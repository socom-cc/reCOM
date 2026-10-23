from __future__ import annotations

from pathlib import Path

import pytest

from tools._socom.type_layout import (
    CallParameters,
    _Family,
    _const,
    _copy_source,
    _join,
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
    assert family.receivers.proof(0x37E560) == "DWARF formal parameter this"  # CLoadState::AbortLoad(char const*)
    # zdb::CCamera::Update(zdb::tag_ZCAM_TYPE): the by-value parameter is a DWARF enumeration, so a static
    # reading settles to a0 alone and the a1 read proves the receiver.
    assert ("zdb", "tag_ZCAM_TYPE") in family.symbols.scalars
    assert family.receivers.proof(0x1E7F30).startswith("reads a1 at 0x1e7f34, beyond the 1 GPR parameter(s)")
    parameters = CallParameters(family.symbols, family.receivers)
    assert parameters.of(0x1FC760, "a1") == {"parameter_type": "Metrowerks::compile_assert<1> const&"}
    # An unproven receiver types a register where the member and static readings agree.
    assert parameters.of(0x30F050, "a1") == {"parameter_type": "_word128*"}
    assert parameters.of(0x30F050, "a3") == {"parameter_unknown": "receiver unproven: _word128* if a member, no parameter if static"}
    assert parameters.of(0x229510, "a1") == {"no_parameter": True}
    assert parameters.of(None, "a0") == {"parameter_unknown": "indirect call: the callee is not known"}


def _sites_at(report: dict, name: str, offset: int) -> dict:
    return {site["site"]: site for site in _offset(_class(report, name), offset)["sites"]}


def _function_roots(report: dict, address: str) -> dict:
    row = next(row for row in report["functions"] if row["function"] == address)
    return {root["register"]: root for root in row["roots"]}


def test_enumeration_parameters_settle_the_registers_after_them() -> None:
    params = demangle("RenderVisual__5CPipeFPQ23zdb5CNodeQ23zdb12tag_ZVIS_FOV")["params"]
    rows, complete = parameter_registers(params, has_this=False)
    assert not complete and [name for name, _value in rows] == ["a0"]
    rows, complete = parameter_registers(params, False, frozenset({("zdb", "tag_ZVIS_FOV")}))
    assert complete and [name for name, _value in rows] == ["a0", "a1"]


def test_joins_widen_loop_pointers_and_register_copies_are_recognized() -> None:
    this = (("arg", 4), 0)
    # One pointer at two offsets is that pointer plus an index, from the lower offset.
    assert _join({5: (("arg", 4), 0x30)}, {5: (("arg", 4), 0x34)}) == {5: (("ix", (("arg", 4), 0x30)), 0)}
    widened = (("ix", (("arg", 4), 0x30)), 0)
    assert _join({5: widened}, {5: (widened[0], 4)}) == {5: widened}
    assert _join({5: _const(1)}, {5: _const(2)}) == {}  # constants never widen
    assert _join({5: this}, {5: (("arg", 5), 0)}) == {}  # different pointers never meet
    assert _join({("s", 8): (this, 4)}, {("s", 8): ((("arg", 4), 4), 4)}) == {("s", 8): ((("ix", this), 0), 4)}
    assert _copy_source(0x02002025, 4) == 16  # or a0,s0,zero (move a0,s0)
    assert _copy_source(0x0200202D, 4) == 16  # daddu a0,s0,zero
    assert _copy_source(0x02002025, 5) is None and _copy_source(0x02112021, 4) is None  # other target; addu a0,s0,s1


def test_holders_type_vector_elements_from_typed_storage_passes(cvisual: dict) -> None:
    storage = {row["storage"]: row for row in cvisual["holders"]["element_storage"]}
    visuals = storage["CVisualVector+0x8"]
    assert visuals["element"] == "zdb::CVisual*"
    # DeleteVisual passes this->m_visual.data_ + an index as remove_copy's zdb::CVisual** a1.
    assert any(
        proof.startswith("DWARF zdb::CNode+0x8c m_visual.data_ (CVisualVector+0x8) + an index passed as a1 (zdb::CVisual**)")
        and proof.endswith("@0x227a48 in zdb::CNode::DeleteVisual(zdb::CVisual*, bool)")
        for proof in visuals["proofs"]
    )
    assert storage["CNodeVector+0x8"]["element"] == "zdb::CNode*"
    assert not cvisual["holders"]["element_conflicts"]


def test_holder_roots_attribute_outside_accesses_with_their_proofs(cvisual: dict) -> None:
    # CPipe::RenderVisual(CNode*, tag_ZVIS_FOV): the enumeration settles a1 = CNode*; s0 = an element of
    # node->m_visual, loaded at the loop head.
    lod = _sites_at(cvisual, "zdb::CVisual", 0x5)
    assert (lod["0x242574"]["root"], lod["0x242574"]["access"]) == ("held@0x242570", "load")
    proof = _function_roots(cvisual, "0x2424f0")["held@0x242570"]["proof"]
    assert proof.startswith("element zdb::CVisual* loaded @0x242570 from [DWARF zdb::CNode+0x8c m_visual.data_ (CVisualVector+0x8)")
    assert proof.endswith("loaded @0x24255c/0x2428ac from [parameter a1 (zdb::CNode*)]]")
    assert _sites_at(cvisual, "zdb::CVisual", 0x0)["0x2427b8"]["field_bits"] == "0x800"
    # CPipe::RenderWorld: CNode::GetFirstVisual() returns NULL or an element of this->m_visual.
    stamp = _sites_at(cvisual, "zdb::CVisual", 0x1C)["0x244bb0"]
    assert (stamp["root"], stamp["access"], stamp["constant"]) == ("return@0x244ba0", "store", -3)
    typed = {row["function"]: row for row in cvisual["holders"]["typed_returns"]}
    assert typed["0x229460"]["returns"] == "zdb::CVisual*"
    assert typed["0x229460"]["proof"].startswith("zdb::CNode::GetFirstVisual(void) returns NULL or a zdb::CVisual* at every exit")
    # Create returns one of four allocations through register copies; their common base is CVisual.
    assert typed["0x30e100"]["returns"] == "zdb::CVisual*"
    # Children's visuals: an element of this->m_child (CNodeVector storage), then an element of its m_visual.
    multipass = _sites_at(cvisual, "zdb::CVisual", 0x1)["0x225944"]
    assert (multipass["root"], multipass["access"]) == ("held@0x225918", "store")
    assert "CNodeVector+0x8" in _function_roots(cvisual, "0x225850")["held@0x225918"]["proof"]
    # Particle::CreateVisuals: the constructor returns this through a stack reload, so the allocation stays typed.
    assert _sites_at(cvisual, "zdb::CVisual", 0x1)["0x23375c"]["root"] == "new@0x2335d0"
    assert "## holders" in render_layout(cvisual) and "element storage CVisualVector+0x8: zdb::CVisual*" in render_layout(cvisual)


def test_holders_leave_untyped_holders_and_look_alikes_unattributed(cvisual: dict) -> None:
    attributed = {site["site"] for cls in cvisual["classes"] for row in cls["offsets"] for site in row["sites"]}
    attributed |= {site["site"] for cls in cvisual["classes"] for site in cls["object_passes"]}
    # CPipe::CAlpha::Render reads its visual from tag_DelayedNode+0x44, but DWARF only declares tag_DelayedNode;
    # CNode::__dt's vptr load is a CDI of m_di; CRipple::Tick stores through CVisData::SelectVertex's result;
    # Destruction_Instance::Create's t0 follows a by-value CPnt3D, so its register is not settled; CGrid and
    # CRipple read fields of their own this.
    for site in ("0x241ddc", "0x241de0", "0x226518", "0x231fbc", "0x2367e4", "0x2367e8", "0x2367ec", "0x212138", "0x231e34"):
        assert site not in attributed, site


# -- plain structs (struct mode) ------------------------------------------------


@pytest.fixture(scope="module")
def object_header(root: Path) -> dict:
    return class_layout(root, "tag_ObjectHeader", struct=True)


def test_struct_mode_lays_out_a_name_proven_only_by_parameter_types(root: Path, object_header: dict) -> None:
    assert object_header["struct"] is True and object_header["with_derived"] is False
    (row,) = object_header["classes"]
    assert (row["class"], row["role"], row["members"], row["vtable"], row["rtti"]) == ("tag_ObjectHeader", "requested", [], None, [])
    assert row["name_evidence"] == [
        "VuBatchProgram_Decals__Q23zdb7CVisualFP8_word128P16tag_ObjectHeader",
        "VuBatchProgram__Q23zdb7CVisualFP8_word128P16tag_ObjectHeaderPQ23zdb17tag_DETAIL_PARAMS",
        "VuObjectSetup__Q23zdb7CVisualFP8_word128P16tag_ObjectHeader",
    ]
    assert [entry["offset"] for entry in row["offsets"]] == [0x0, 0x4, 0x8, 0xC, 0x10]
    # Callee side: the typed a2 parameter (the program qword count, then bit 0 of +0xc).
    assert _sites_at(object_header, "tag_ObjectHeader", 0x4)["0x30c340"]["root"] == "param a2"
    bitfield = _sites_at(object_header, "tag_ObjectHeader", 0xC)["0x30c6b4"]
    assert bitfield["bitfield"]["field_mask"] == "0x1" and bitfield["root"] == "param a2"
    # VuObjectSetup's s0 is a1 (_word128 *), not the header: its word 0 = 63 store is not header evidence.
    assert "0x30c398" not in _sites_at(object_header, "tag_ObjectHeader", 0x0)
    # Caller side: VuUpdate passes zSysSprGetPacket()+0x10 as a2 and +0x30 as a1 (_word128 *).
    zero = _sites_at(object_header, "tag_ObjectHeader", 0x10)["0x30a96c"]
    assert (zero["width"], zero["kind"], zero["root"]) == (16, "zero", "built@0x30a978")
    count = _sites_at(object_header, "tag_ObjectHeader", 0x8)["0x30ae58"]
    assert (count["access"], count["width"], count["root"]) == ("store", 4, "built@0x30adf4")
    regions = row["caller_built"]["regions"]
    assert len(regions) == 8 and {region["status"] for region in regions} == {"attributed"}
    assert {region["extent_bound"] for region in regions} == {0x20}
    assert all("passed as a1 (_word128 *)" in region["bound"] for region in regions)
    assert row["caller_built"]["flagged"] == []
    bounds = row["size_bounds"]
    assert (bounds["largest_attributed_extent"], bounds["region_bounds"], bounds["allocation_sizes"]) == (0x20, [0x20], [])
    roots = _function_roots(object_header, "0x30a900")
    assert roots["built@0x30a978"]["proof"].startswith("result of zSysSprGetPacket(uint16**) @0x30a954+0x10 passed as a2")
    text = render_layout(object_header)
    assert "(plain struct)" in text and "caller-built regions (8):" in text and "flagged, not attributed (0):" in text
    assert canonical_json(class_layout(root, "tag_ObjectHeader", struct=True)) == canonical_json(object_header)


def test_struct_mode_refuses_names_it_does_not_cover(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools._socom import type_layout

    with pytest.raises(SocomError, match=r"lay it out as a plain struct \(--struct\)"):
        _Family(root, "tag_ObjectHeader", with_derived=False)
    with pytest.raises(SocomError, match="lay it out as a class"):
        _Family(root, "zdb::CVisual", with_derived=False, struct=True)
    with pytest.raises(SocomError, match="no derived classes"):
        _Family(root, "tag_ObjectHeader", with_derived=True, struct=True)
    with pytest.raises(SocomError, match="no mangled function parameter"):
        _Family(root, "tag_NoSuchStruct", with_derived=False, struct=True)
    monkeypatch.setattr(type_layout, "dwarf_sizes", lambda _root: {"tag_ObjectHeader": [32]})
    with pytest.raises(SocomError, match="DWARF has a record"):
        _Family(root, "tag_ObjectHeader", with_derived=False, struct=True)


class _FakeCtx:
    object_starts = [0x500000]
    objects = {0x500000: (0x30, "g_object")}

    def object_for(self, address: int) -> str:
        return f"g_object+0x{address - 0x500000:x}"

    def label(self, address: int) -> str:
        return f"0x{address:x}"

    def text(self, site: int) -> str:
        return f"insn@{site:x}"


class _FakeSymbols:
    def readable(self, address: int | None) -> str:
        return f"f_{address:x}" if address is not None else "indirect"

    def parsed(self, address: int | None) -> dict:
        return {"name": "__nw", "qualifier": []} if address == 0x100 else {}


def _fake_collector() -> object:
    from collections import defaultdict
    from types import SimpleNamespace

    from tools._socom.type_layout import _Collector

    collector = object.__new__(_Collector)
    collector.family = SimpleNamespace(requested=("tag_S",), root=Path("."))
    collector.ctx, collector.symbols = _FakeCtx(), _FakeSymbols()
    collector.allocations = defaultdict(list)
    collector.region_rows, collector.flagged, collector.regions = [], [], {}
    collector._sizes = {"CPnt3D": [12]}
    return collector


def _pass(site: int, register: str, key: tuple | None) -> dict:
    return {"site": site, "register": register, "callee": 0x200, "type": key}


def _event(site: int, address: tuple, width: int, store: bool = False) -> dict:
    return {"site": site, "address": address, "width": width, "kind": "int", "signed": None, "store": store, "value": None, "loaded": None}


def _no_flow(**fields: object) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(**{"calls": [], "memory": [], "frame": [], "flow": None, **fields})


def test_caller_built_regions_are_bounded_or_refused_and_flag_what_they_cannot_attribute() -> None:
    struct, point, sp = ("class", ("tag_S",)), ("class", ("CPnt3D",)), ("sp",)
    collector = _fake_collector()
    # A frame object at entry sp-0x40, bounded by a CPnt3D passed at sp-0x20; a CPnt3D at sp-0x48 overlaps +0x0..+0x4.
    points = {-0x48: [_pass(0x10, "a1", point)], -0x40: [_pass(0x20, "a0", struct)], -0x20: [_pass(0x20, "a1", point)]}
    collector._region(0x1000, _no_flow(), sp, -0x40, points)
    (row,) = collector.region_rows
    assert (row["status"], row["extent_bound"], row["ambiguous_below"]) == ("attributed", 0x20, 4)
    assert row["bound"] == "entry sp-0x20 passed as a1 (CPnt3D *) of f_200 @0x20"
    cls, offset, root, path = collector._region_at(0x1000, (sp, -0x38))
    assert (cls, offset, path) == (("tag_S",), 8, [])
    assert collector._admit(0x1000, 0x30, root, [], 8, 4, "load")
    assert not collector._admit(0x1000, 0x34, root, [], 0x1C, 8, "store")  # passes the region end
    assert not collector._admit(0x1000, 0x38, root, [], 0, 4, "store")  # where the lower CPnt3D may extend
    assert not collector._admit(0x1000, 0x3C, root, ["[i]"], 8, 4, "load")  # indexed from its start
    assert [flag["site"] for flag in collector.flagged] == ["0x34", "0x38", "0x3c"]
    assert collector._region_at(0x1000, (sp, -0x20)) is None
    # The same address also passed as another type: the slot is reused, nothing is attributed, its accesses are flagged.
    collector = _fake_collector()
    reused = {-0x40: [_pass(0x40, "a0", struct), _pass(0x48, "a0", point)], -0x20: [_pass(0x40, "a1", None)]}
    collector._region(0x1000, _no_flow(frame=[_event(0x44, (sp, -0x3C), 4)]), sp, -0x40, reused)
    assert collector.region_rows[0]["status"] == "refused" and "also passed as CPnt3D *" in collector.region_rows[0]["reason"]
    assert collector.regions == {} and [(flag["site"], flag["offset"]) for flag in collector.flagged] == [("0x44", 4)]
    # A call result that nothing bounds is refused; operator new(0x18) bounds one and is its size evidence.
    collector = _fake_collector()
    unbounded = ("res", 0x60)
    analysis = _no_flow(calls=[{"site": 0x60, "callee": 0x300, "arguments": {}}], memory=[_event(0x70, (unbounded, 0x40), 4, True)])
    collector._region(0x1000, analysis, unbounded, 0, {0: [_pass(0x68, "a1", struct)]})
    assert collector.region_rows[0]["status"] == "refused" and "nothing bounds" in collector.region_rows[0]["reason"]
    assert [(flag["site"], flag["offset"]) for flag in collector.flagged] == [("0x70", 0x40)]
    allocated = ("res", 0x80)
    analysis = _no_flow(calls=[{"site": 0x80, "callee": 0x100, "arguments": {"a0": (("const",), 0x18)}}])
    collector._region(0x1000, analysis, allocated, 0, {0: [_pass(0x88, "a0", struct)]})
    assert (collector.region_rows[1]["extent_bound"], collector.region_rows[1]["bound"]) == (0x18, "operator new(0x18) @0x80")
    assert [row["size"] for row in collector.allocations[("tag_S",)]] == [0x18]
    # A global object ends at its symbol's size; an address in the caller's frame is refused.
    collector = _fake_collector()
    collector._region(0x1000, _no_flow(), ("sym", 0x500000), 0x500010, {0x500010: [_pass(0x90, "a0", struct)]})
    assert (collector.region_rows[0]["extent_bound"], collector.region_rows[0]["bound"]) == (0x20, "the end of g_object (0x30 bytes)")
    collector._region(0x1000, _no_flow(), sp, 0x8, {0x8: [_pass(0x98, "a0", struct)]})
    assert collector.region_rows[1]["status"] == "refused" and "caller's frame" in collector.region_rows[1]["reason"]
