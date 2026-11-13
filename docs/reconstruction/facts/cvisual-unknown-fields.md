# zdb::CVisual fields +0x5, +0x6, +0x7, +0x1c: every access in socom.elf

Read-only evidence search (2026-10-23). Nothing in Ghidra, the tracker, or any
tracked file was changed. Offsets are from the start of a `zdb::CVisual`
object. `zdb::tag_VIS_PARAMS` is the base at +0 (0x18 bytes). In this file,
the "class family" means member functions of `zdb::CVisual`, `zdb::CMesh`,
`zdb::CSubMesh`, `C2DVisual`, and `zdb::tag_VIS_PARAMS`.

## Method and coverage

Evidence came from `python tools/socom.py recon asm` (all 9,703 functions in
`build/recon-graph.json`), `recon dwarf`, `recon bytes`, `recon refs`, and the
existing `build/type-plans/zdb-cvisual-layout.json`. A scratch CFG data-flow
pass, union over paths and interprocedural, followed family pointers from
these sources:

1. `this`, allocation results (`__nw` passed to a family constructor), and
   family-typed parameters in every mangled signature in the ELF.
2. `zdb::CNode::m_visual`, a DWARF `CNode` member at +0x84 with type
   `CVisualVector` (12 bytes: size at +0x88, data at +0x8c). The pass
   followed it through inline `lw x,0x8c(node)`, through `node+0x84` passed to
   `std::__vector_pod<Ui>::data/begin/end/operator[]`, and then through element
   loads. This was done for any base register, typed or not.
   - Element type proof: `zdb::CVisualVector::Exists(zdb::CVisual const*)`
     (0x224460) compares the elements at `data` (+8) with its `CVisual const*`
     parameter. `zdb::CNode::AddVisual(zdb::CVisual*)` (0x227b40) inserts its
     parameter into `this+0x84`.
3. Return values (to a fixpoint):
   - `CNode::GetFirstVisual` 0x229460, `GetSubMesh` 0x229490, `GetMesh` 0x229510;
   - `CVisual::Create` 0x30e100 and `CMesh::Clone` 0x30f330;
   - `__dynamic_cast` of a family pointer;
   - virtual slot +0x20 (`Get2DVisual`) through the vptr at +0x20;
   - any function that returns one of these.
4. Values passed in argument registers into any callee, stack spills and
   reloads, and gp globals that receive one. The only real global is the
   static `last_mesh$1263` (0x227ff0, inside `CNode::_Copy`).
5. Holder fields, found from stores of proven pointers. The pass cannot type
   these structures, so every reader was checked by hand:
   - `tag_DelayedNode`+0x44: `CPipe::CAlpha::Add` 0x2420d4 stores its
     `CVisual*` a3; `CPipe::CAlpha::Render` reads it at 0x241dd8 and 0x241ee0.
   - `CDecal`+0x4: written at 0x312eac, read at 0x3133a8.
   - `CTextureFX`+0x8: written at 0x3142fc, read at 0x313c44.
   - `CRipple`+0x30: read at 0x231f7c.
   - `CMeshDecal`+0x8: read at 0x3131d8.
   - `CSubMesh`+0x6c (`CMesh*`): written at 0x30ef84.
   - `CMesh`+0x68: written at 0x30f550, read at 0x30f1dc.
   - The local visual vector on the stack in `hookupVisuals`.

   None of these readers touches +0x5, +0x6, +0x7, or +0x1c. Each one only
   passes the pointer on to a family function.

The completeness check covered every ELF call to a family member, or to a
function with a family-typed parameter, and asked whether the argument was
traced. 32 sites stay untraced, and every one is explained:

- 6 pass a literal NULL. These are `RenderMesh` a2 at 0x218d4c, 0x241bfc,
  0x243b54, and 0x245900; `RenderMeshShadow` a2 at 0x2449dc; and the
  `CSubMesh` ctor a1 at 0x30e1e4.
- 20 call static members, where a0 is not an object:
  - `CVisual::Create` (a0 = `zar::CZAR&`) ×2;
  - `Init` ×2, `AlphaEnable` ×3, `LandmarkEnable` ×2, `NodeSetup` ×4 (a0 is
    a `CNode*`), and `AddLocalLight`;
  - `Flush`, `GetTextureSelectBlock`, `GetTextureSelectBlock_ver2`, and
    `SaveTextureSelect`;
  - `CTextureFX::InTexfxpool`. Its visual is in a0, an element of
    `this->m_visual` in `CNode::ScrollTexture`; only +0x4 is read there.
  - `Particle::Destruction_Instance::Create`. The `CVisual*` is in a3, the new
    object from `Particle::CreateVisuals`; t0 is a `CPnt3D*`.
- 6 are the holder reads listed above.

Indirect `jalr` calls get no real family pointer except through the family
vtable slots. No ELF data initializes these fields. Family vtables are
referenced only by the ctors and dtors and by `CMesh::Clone`. `recon refs`
shows no data relocation to them outside the vtables themselves. No static
family object exists: every object comes from `__nw` plus a ctor, or from ZAR
data through `Read`.

## +0x5 (1 byte)

| Site | Function | Instruction | R/W | Value / use | Pointer proof |
|---|---|---|---|---|---|
| 0x30e074 | zdb::CVisual::__ct | `sb zero,5(v0)` | W | 0 | ctor `this` (v0 reloaded from sp+104) |
| 0x30f6a4 | zdb::tag_VIS_PARAMS::operator= | `lbu v1,5(a1)` | R | copied to the next row | a1 = `tag_VIS_PARAMS const&` parameter |
| 0x30f6a8 | zdb::tag_VIS_PARAMS::operator= | `sb v1,5(a0)` | W | source byte | a0 = `this`; only caller is `CMesh::Clone` 0x30f42c (dst = new clone, src = `this` CMesh) |
| 0x30d118 | zdb::CVisual::Write | `jal zar::CZAR::Insert("vparams", this, 24)` | R (bytes 0..0x17) | serialized | `this` (vtable slot +0x1c); key string at 0x459880 = "vparams" |
| 0x30d158 | zdb::CVisual::Read | `jal zar::CZAR::Fetch("vparams", this, 24)` | W (bytes 0..0x17) | ZAR file data | `this` (vtable slot +0x18); reached by `CMesh::Read` (tail jump 0x30f140) and `CSubMesh::Read` (0x30eec0) |
| **0x242574** | CPipe::RenderVisual(CNode*, tag_ZVIS_FOV) | `lbu v0,5(s0)` | R | `beq v0,zero,0x242600`: 0 skips the LOD-band test and goes straight to the draw path | s0 = `lw 0(s2)` at 0x242570; s2 = `lw 0x8c(a1)` at 0x24255c, the data of `CNode::m_visual`; a1 = `CNode*` from the mangled signature. The same s0 is the receiver of `CVisual::DrawLOD` (0x2425dc), the `CVisual*` a3 of `CPipe::CAlpha::Add` (0x24282c), and a0 of vtable slot +0xc `Render` through the vptr at +0x20 (0x242888..0x242894) |
| **0x242590** | CPipe::RenderVisual | `lbu v1,5(s0)` | R | Used as a 1-based index. See the LOD-band paragraph after this table | same s0 |
| **0x242c10** | CPipe::RenderNodeShadow(CNode*) | `lbu v1,5(s0)` | R | Same LOD-band pattern as 0x242590. 0 jumps straight to `Render` (0x242c88). Otherwise it builds the band (0x242c1c..0x242c50), calls `DrawLOD(band, rangeSq, sp+124)` at 0x242c78, and a 0 result skips the shadow `Render` | s0 = `lw 0(s2)` at 0x242c0c; s2 = `lw 0x8c(s3)` at 0x242bf8; s3 = a1 `CNode*` (signature). s0 is the receiver of `DrawLOD` (0x242c78) and of vtable slot +0xc (0x242c94) |

LOD-band lookup at 0x242590 (reads +0x5):

- The table is `CPipe::m_world`, loaded with `lw v0,1572(s4)` (DWARF `m_world`,
  `CWorld*` at +0x624). The pass adds 0x568, which is DWARF
  `CWorld::m_LOD_Object`, a `CLOD_Object` whose vector base holds the size at
  +4 and the data at +8.
- If size < value, the band is NULL and the visual is drawn without the test.
- Otherwise band = data + (value−1)×32 (32 = DWARF `CLOD_band` size). The
  band is passed as a1 to `CVisual::DrawLOD(CLOD_band*, float rangeSq, float*)`
  at 0x2425dc.
- If `DrawLOD` returns 0, the visual is not drawn (0x2425e4..0x2425fc, branch
  to 0x2428a8). Otherwise drawing continues at 0x242600.

## +0x6 (1 byte)

| Site | Function | Instruction | R/W | Value / use | Pointer proof |
|---|---|---|---|---|---|
| 0x30e064 | zdb::CVisual::__ct | `sb zero,6(v0)` | W | 0 | ctor `this` |
| 0x30f6ac | zdb::tag_VIS_PARAMS::operator= | `lbu v1,6(a1)` | R | copied to the next row | a1 = `tag_VIS_PARAMS const&` |
| 0x30f6b0 | zdb::tag_VIS_PARAMS::operator= | `sb v1,6(a0)` | W | source byte | `this` (`CMesh::Clone` only) |
| 0x30d118 | zdb::CVisual::Write | Insert "vparams", 24 bytes | R | serialized | `this` |
| 0x30d158 | zdb::CVisual::Read | Fetch "vparams", 24 bytes | W | ZAR file data | `this` |

No other access exists anywhere in the ELF, inside or outside the class family.

## +0x7 (1 byte)

| Site | Function | Instruction | R/W | Value / use | Pointer proof |
|---|---|---|---|---|---|
| 0x30e06c | zdb::CVisual::__ct | `sb zero,7(v0)` | W | 0 | ctor `this` |
| 0x30f6b4 | zdb::tag_VIS_PARAMS::operator= | `lbu v1,7(a1)` | R | copied to the next row | a1 = `tag_VIS_PARAMS const&` |
| 0x30f6b8 | zdb::tag_VIS_PARAMS::operator= | `sb v1,7(a0)` | W | source byte | `this` (`CMesh::Clone` only) |
| 0x30d118 | zdb::CVisual::Write | Insert "vparams", 24 bytes | R | serialized | `this` |
| 0x30d158 | zdb::CVisual::Read | Fetch "vparams", 24 bytes | W | ZAR file data | `this` |

No other access exists anywhere in the ELF, inside or outside the class family.

## +0x1c (word)

| Site | Function | Instruction | R/W | Value / use | Pointer proof |
|---|---|---|---|---|---|
| 0x30e084 | zdb::CVisual::__ct | `sw t2,28(v0)` | W | 3 (`li t2,3` 0x30df6c) | ctor `this` |
| 0x30fa14 | zdb::CMesh::__ct | `sw a1,28(v1)` | W | 3 (`li a1,3` 0x30f9fc), after `CVisual::__ct` | ctor `this` (sp+44) |
| 0x30ef74 | zdb::CSubMesh::__ct(CMesh*) | `sw v0,28(s1)` | W | 3 (`li v0,3` 0x30ef70) | ctor `this` |
| 0x30f3bc | zdb::CMesh::Clone | `sw a1,28(v1)` | W | 3 (inlined `CMesh` ctor) | v1 = sp+136 = `__nw(0x8c)` 0x30f354, built by `CVisual::__ct` 0x30f368 plus `__vt__Q23zdb5CMesh` 0x30f37c |
| 0x30f444 | zdb::CMesh::Clone | `lw v0,28(s3)` | R | stored at 0x30f44c | s3 = `this` |
| 0x30f44c | zdb::CMesh::Clone | `sw v0,28(s0)` | W | source mesh's value | s0 = the clone |
| 0x30d17c | zdb::CVisual::Read | `sw v0,28(s1)` (delay slot) | W | −2 (`li v0,-2` 0x30d174) when byte +1 bit 2 is set (word bit 10, `lbu v0,1(s1)` / `dsll32 29` / `dsrl32 31`, 0x30d160..0x30d16c, right after the "vparams" Fetch) | `this` |
| 0x30d180 | zdb::CVisual::Read | `sw v0,28(s1)` | W | 3 (`li v0,3` 0x30d170) when that bit is clear | `this` |
| 0x30bdd4 | zdb::CVisual::VuBatchProgram | `lw t3,28(a0)` | R | `bne t3,3,0x30c250` (0x30bddc). ==3: the long VU program-id list at 0x30bde4 (type/byte2-gated 82+102 or 104/112, fov, fog, lighting/local lights, scale colour, multipass 114, detail ranges 48, shadow maps 60, light maps 56, 116). ≠3: the short list at 0x30c250 (72, 4, 12, fog 20, lighting 88+28, 44, 78). Both end with 66 at 0x30c314 | `this` (layout tool: a3 read beyond static parameters) |
| 0x30c370 | zdb::CVisual::VuObjectSetup | `lw v1,28(a0)` | R | `bne v1,-2,0x30c39c` (0x30c388). ==−2: `tag_ObjectHeader` word 0 = 63 (0x30c390/0x30c398). Otherwise word 0 = `m_fovClipWord >> 8` (0x30c39c..0x30c3a4). The header is a1 (s0) | `this` |
| **0x244bb0** | CPipe::RenderWorld(CWorld*) | `sw v1,28(v0)` | W | −3 (`li v1,-3` in the delay slot at 0x244bac). Stored only when the visual is non-NULL (0x244ba8). Next comes the virtual `Render`: `lw t9,32(v0)`, slot +0xc, a0 = v0, a1 = `CStack::m_top` (0x244bb4..0x244bc0) | v0 = `CNode::GetFirstVisual(s0)` at 0x244ba0, which returns `m_visual` data[0] or NULL. s0 = `CPipe::m_cell` (`lw s0,1580(s4)` 0x244b3c; DWARF `m_cell` is `CCell*` at +0x62c, and `CCell` derives from `CNode`), set from `CGridAtom::GetCell` 0x244b28/0x244b38 |
| **0x244ea0** | CPipe::RenderWorld | `sw v1,28(v0)` | W | −3 (`li v1,-3` 0x244e9c), then the virtual `Render` (0x244ea4..0x244eb0) | v0 = `GetFirstVisual(s1)` 0x244e90; s1 = the `GetCell` result 0x244e04, also stored to `m_cell` at 0x244e18 |

`Write` stores only 24 bytes (+0..+0x17, `li a3,24` at 0x30d114), so +0x1c is
never serialized. `CVisual::Read` 0x30d160 is the only place in the ELF that
reads the word +0 bit 10 that selects −2.

## Rejected candidates (not CVisual-family pointers)

- **Analysis artefacts.** None of these is a real CVisual-family pointer:
  - The static `CVisual::Create`'s a0 is a `zar::CZAR&`. This explains:
    - `zar::CZAR::GetOpenKey` 0x1d8d30 and `CloseKey` 0x1d8f18/0x1d8f2c;
    - list `insert` 0x17c710/0x17c718 and `erase` 0x1804e8/0x1804f0.
  - `_free_r` 0x3e0bb0..0x3e0e28 reads heap chunk headers.
  - `CMission::PreOpen` 0x1f8b9c.. reads the `strcpy` result.
  - `Destruction_Instance::Create` 0x2367e8 `lwc1 f1,4(t0)` reads the
    `CPnt3D*` in t0.
  - `CMesh`+0x6c is the `CMeshDecal` list (next at +4), not a mesh. Its
    accesses are in `VuUpdate` 0x30b590, `CMesh::DereferenceDecals`,
    `RemoveMeshDecal`, and `__dt`.
- **Offset matches with a different base:**
  - `CNode::__dt` 0x226518 `lw t9,28(s3)`: the vptr of a `CDI` from `m_di`.
  - `CGameMenu::LoadFromDesign` 0x3826d4/0x382a2c: vtable slots.
  - `CGameMenu::LoadFromDesign` 0x382b2c: `CGameDlgDesign`+0x1c (a1 saved
    at sp+188).
  - `CDecal::AddDecal` 0x312fc8..: `AddonPoint`+0x1c.
  - `CRipple::Tick` 0x231e34 and `CGrid::InitDescendantsVisuals` 0x212138:
    `this` fields.
  - `CRipple::Tick` 0x231fbc `sh v0,6(a2)`: the `CVisData::SelectVertex` result.

## What the code shows

- **+0x5:** An unsigned byte. It is 0 after construction; otherwise it comes
  from the ZAR "vparams" block, and `Clone` copies it. Only
  `CPipe::RenderVisual` and `CPipe::RenderNodeShadow` read it.
  - 0 means no LOD-band test.
  - N > 0 selects band N−1 of the world's `CWorld::m_LOD_Object` band vector,
    with an unsigned bounds check. Out of range is treated as no band.
  - `CVisual::DrawLOD` tests that band against the camera range squared and
    may scale the fade. False means the visual or its shadow is not drawn.
  - The value is used as a count-like index, not as a 0/1 flag.
- **+0x6:** Written only as 0 by the ctor, loaded from ZAR data, and copied by
  `tag_VIS_PARAMS::operator=` (bytewise, unsigned) and by Write/Read. No code
  in the ELF reads it for any decision. The code does not show what it means.
- **+0x7:** Same as +0x6: only the ctor zero, the ZAR load, the copy, and
  serialization. It is never read for a decision. The code does not show what
  it means.
- **+0x1c:** A signed word with three values:
  - 3 from the CVisual, CMesh, and CSubMesh ctors, from `Clone`, and from
    `Read` when +0 bit 10 is clear;
  - −2 from `Read` when that bit is set;
  - −3 stored by `CPipe::RenderWorld` on each grid cell's first visual just
    before rendering it, every frame. This overwrites the value from `Read`.

  It has two readers, both in the VU path (`Render` → `VuUpdate` →
  `VuObjectSetup` / `VuBatchProgram`):
  - `VuBatchProgram`: ==3 selects the full VU program list; any other value
    selects the reduced list without shadow, light-map, detail, multipass, or
    scale-colour entries.
  - `VuObjectSetup`: ==−2 forces object-header word 0 to 63; any other value
    uses `m_fovClipWord >> 8`.

  So −3 behaves as "not 3 and not −2". The word is never serialized.
## Word +0x0 (bits) and +0x8/+0xa (m_unk08): every access

This search used the same analyzer, the same pointer sources and the same
hand-checked holder readers as above. Its target was any access whose bytes
overlap +0x0..+0x3 or +0x8..+0xb. Bit numbers count from the LSB of the
little-endian word at +0: byte +1 bit k is word bit 8+k, and byte +2 bit k is
word bit 16+k. A mask is mapped to bits directly (for example `andi 0x2000` is
bit 13). A shift pair `dsll32 n` / `dsrl32 31` on byte b selects byte bit
31−n, which is word bit 8b+31−n.

"In-family" means a site the plan `build/type-plans/zdb-cvisual.json` already
cites, or the load or store half of a cited read-modify-write. "New" means a
site outside the class family that the plan does not cite. Pointer proofs used
in the tables:

- **N**: the pointer is an element of `zdb::CNode::m_visual` (DWARF member at
  +0x84, `CVisualVector`). This document's first section gives the element-type
  proof.
- **RV**: s0 in `CPipe::RenderVisual(CNode*, tag_ZVIS_FOV)`. It is loaded with
  `lw 0(s2)` at 0x242570, where s2 = `lw 0x8c(a1)` at 0x24255c and a1 is the
  mangled `CNode*`. The same s0 is the receiver of `CVisual::DrawLOD`, the a3 of
  `CPipe::CAlpha::Add(CNode*, CNode*, CVisual*, ...)`, and the a0 of vtable
  slot +0xc.
- **PV**: s1 in `Particle::CreateVisuals`. It is the `__nw(104)` result
  (0x2335d0/0x2335d8) passed as `this` to `CVisual::__ct` at 0x2335e4.
- **AL**: in `CPipe::CAlpha::Render`, v1 = `lw 68(s0)` at 0x241dd8, where s0
  is a delayed node from the list at `CAlpha`+12.
  - `CAlpha::Add` takes a 112-byte node from `this`+8 (0x24202c..0x242034). It
    stores its mangled `CVisual*` a3 (s2) at node+0x44 (0x2420d4). It then
    inserts the node into the list at `this`+12 (0x2422d0..0x2422e0).
  - `Render` passes the same +0x44 value as receiver a0 to `CVisual::VuUpdate`
    (0x241edc/0x241ee0).

The CNode functions that write bits 14 and 16 have a second loop that walks
`m_child` (DWARF `CNodeVector` at +0x68; data `lw s0,112(s5)`). That loop
works on each child node's own `m_visual`, then recurses into grandchildren by
calling the same `CNode` member with them as `this` (0x225994 and 0x225b54).

### Bit 0 (plan m_flag0)

| Site | Function | Instruction | R/W/T | Value / use | Proof | Class |
|---|---|---|---|---|---|---|
| 0x227bc8 | zdb::CNode::AddVisual(CVisual*) | `lw v0,0(s1)` + `andi 0x1` | T | Bit 0 set and bit 8 clear → set the node's `m_transparent` (byte +0x5c bit 7) | mangled param a1 | in-family (cited) |
| 0x228174 | zdb::CNode::_Copy | `lw v0,0(s1)` | T | Same test and node mark (0x228178..0x22818c) | new `CSubMesh` (`__nw(0x70)` 0x2280e8 + ctor 0x228100) | in-family (cited) |
| 0x236a00 | Particle::Destruction_Instance::__ct | `lw a0,0(s0)` | T | Same test (0x236a0c..0x236a28) | mangled param t0 | in-family (cited) |
| **0x228054** | zdb::CNode::_Copy | `lw v0,0(s1)`, `andi v0,0x1` (0x228060) | T | Bit 0 && !bit 8 (`sltiu`/`and` 0x228064/0x228068) → `this` node byte +0x5c bit 7 = 1, i.e. `m_transparent` (0x228074..0x228088) | s1 = `last_mesh$1263` = `CMesh::Clone` result (0x227fe8..0x227ff4) | new |
| **0x22825c** | zdb::CNode::_Copy | `lw v0,0(s1)`, `andi v0,0x1` (0x228268) | T | Same test and mark (0x22826c..0x228290), for a visual added without cloning | s1 = source node's `m_visual` element (N, `lw s0,140(s4)` 0x227f94, `lw s1,0(s0)` 0x227f98) | new |
| **0x2336bc / 0x2336d0** | Particle::CreateVisuals | `lbu a0,0(s1)`, `and` with −2, `or` v1, `sb v0,0(s1)` | W | = texture `m_transparent` && !texture `m_bumpmap` | PV | new |

The texture value used at 0x2336bc/0x2336d0 comes from 0x2336d4..0x2336f8 /
0x233694..0x2336b8: `lbu 15` of `CTexHandle::m_texture` (`lw a0,12(s7)`; s7 =
mangled `CTexHandle*` t3, 0x232ec0). That is DWARF `TEXTURE_PARAMS` word +0xc
bit 24 = `m_transparent` and bit 27 = `m_bumpmap`.

### Bit 1 (plan m_flag1)

| Site | Function | Instruction | R/W/T | Value / use | Proof | Class |
|---|---|---|---|---|---|---|
| 0x30df80 | zdb::CVisual::__ct | byte +0 `and 0xfd`, `or 0x2` | W | 1 | `this` | in-family (cited) |
| **0x242610** | CPipe::RenderVisual | `lw v0,0(s0)`, `andi v0,0x2` (0x242614), `sltu` | T | `CVisual::m_fogEnable` (gp-30712, `sb` at 0x24261c) = `CPipe::m_doFog` (DWARF +0x63f, `lbu 1599(s4)` 0x242600) && bit 1. That static gates the fog entries in `VuBatchProgram` (16 / 20) | RV | new |

### Bit 8 (plan m_flag8)

| Site | Function | Instruction | R/W/T | Value / use | Proof | Class |
|---|---|---|---|---|---|---|
| 0x227bcc | zdb::CNode::AddVisual | `andi v1,v0,0x100` | T | Vetoes the bit-0 node mark | a1 | in-family (cited) |
| 0x228178 | zdb::CNode::_Copy | `andi 0x100` | T | Same veto | new `CSubMesh` | in-family (cited) |
| 0x236a0c | Destruction_Instance::__ct | `andi 0x100` | T | Same veto | t0 | in-family (cited) |
| **0x228058 / 0x228260** | zdb::CNode::_Copy | `andi v1,v0,0x100` | T | Same veto (`sltiu v1,v1,1` then `and`) | as in bit 0 | new |
| **0x233674 / 0x233690** | Particle::CreateVisuals | `lbu v1,1(s1)`, `and` with −2 (byte +1 bit 0), `or` (texture `lbu 15`, `dsll32 28` / `dsrl32 31` = byte bit 3), `sb v0,1(s1)` | W | = texture `m_bumpmap` (`TEXTURE_PARAMS` bit 27) | PV | new |

The plan's note "bit 8 never written outside vparams" is contradicted by
0x233690.

### Bit 11 (not in the plan)

| Site | Function | Instruction | R/W/T | Value / use | Proof | Class |
|---|---|---|---|---|---|---|
| **0x233730 / 0x23375c** | Particle::CreateVisuals | `lbu t0,1(s1)`, `and` with −9 (byte +1 bit 3), `or (v0&1)<<3`, `sb v0,1(s1)` (delay slot of `SelectVertex` 0x233758) | W | = texture `m_transparent` && !`m_bumpmap` && (!`m_transp_1bit` (bit 29, `dsll32 26`) \|\| `m_bilinear` (bit 28, `dsll32 27`)); computed at 0x2336d4..0x23372c | PV | new |
| **0x2427b4** | CPipe::RenderVisual | `lw v0,0(s0)`, `andi v0,0x800` (0x2427b8), `bne` → 0x2427ec | T | Unless `CPipe::m_doUI` is set (0x2427a8), a set bit 11 sends the visual to the deferred path at 0x2427ec. That path is also reached when opacity < 1.0 or the near-bilinear flag s1 is set. There, if `CPipe::m_simpletrans` (+0x63d) is clear and opacity > 1/128, it calls `CPipe::CAlpha::Add(…, node, visual, fov, opacity)` (0x24282c) plus `CDynTexList::Add`. Otherwise it is drawn at once (0x242848: NodeSetup + vtable `Render`) | RV | new |

### Bit 13 (not in the plan)

| Site | Function | Instruction | R/W/T | Value / use | Proof | Class |
|---|---|---|---|---|---|---|
| **0x2426bc** | CPipe::RenderVisual | `lw v0,0(s0)`, `andi v0,0x2000` (0x2426c0) | T | Applies only if `CVisual::m_adjustBilinearRange` > 0 (0x2426a0..0x2426b4). It computes the scaled range² of the visual's +0xc point. Inside the range it sets s1 = 1, which forces the deferred (alpha) path above (0x2426f0..0x242704). Outside the range it calls `CVisData::SetBilinear(&_vdataTex, visual +0x30 vector data[vid], 0)`, with vid from the `m_stack_vid` deque top (0x242708..0x24279c) | RV | new |
| **0x241ddc** | CPipe::CAlpha::Render | `lw v0,0(v1)`, `andi v0,0x2000` (0x241de0) | T | Set → `CVisData::SetBilinear(&_vdataTex, visual +0x30 data[node +0x60 bits 3..15], 1)` (0x241dec..0x241e18) before the deferred draw | AL | new |

### Bit 14 (plan m_multipass_enable)

| Site | Function | Instruction | R/W/T | Value / use | Proof | Class |
|---|---|---|---|---|---|---|
| 0x30e00c | zdb::CVisual::__ct | byte +1 `or 0x40` | W | 1 | `this` | in-family (cited) |
| 0x30ab9c / 0x30aba0 | zdb::CVisual::VuUpdate | `andi 0x4000` | T | `_DoMultipass` | `this` | in-family (cited) |
| 0x30c8ac / 0x30c8b0 | zdb::CVisual::GetChainData | `andi 0x4000` | T | Detail qword count | `this` | in-family (cited) |
| **0x2258a4 / 0x2258b4** | zdb::CNode::SetApplyMultipassEffects(bool) | `lbu v1,1(a0)`, `and` with −65 (byte +1 bit 6), `or (b&1)<<6`, `sb v1,1(a0)` | W | = argument b, for every visual of `this` | N (`lw a3,140(s5)` 0x225884; s5 = `this`) | new |
| **0x225930 / 0x225944** | zdb::CNode::SetApplyMultipassEffects | Same RMW on `lbu a1,1(a2)` / `sb v0,1(a2)` | W | = b, for every visual of each child node | N (child `+0x84` data 0x2258e4..0x2258f0, element `lw a2,0(s2)` 0x225918) | new |

The only external caller of `SetApplyMultipassEffects` is `zdb::CClutter::Read`
0x218ef0, which passes b = 0 for the clutter's node. The function also recurses
into grandchildren (0x225994).

### Bit 16 (plan m_flag16)

| Site | Function | Instruction | R/W/T | Value / use | Proof | Class |
|---|---|---|---|---|---|---|
| 0x30e034 | zdb::CVisual::__ct | byte +2 `or 0x1` | W | 1 | `this` | in-family (cited) |
| **0x225a60 / 0x225a70** | zdb::CNode::SetApplyDecals(bool) | `lbu v1,2(a0)`, `and` with −2, `or (b&1)`, `sb v1,2(a0)` | W | = b, for every visual of `this` | N (`lw a3,140(s5)` 0x225a44) | new |
| **0x225aec / 0x225b00** | zdb::CNode::SetApplyDecals | Same RMW for child nodes' visuals (recursion at 0x225b54) | W | = b | N (child `+0x84` 0x225aa4..0x225ab0, element 0x225ad8) | new |
| **0x225480** | zdb::CNode::ApplyDecal(CNode*, float, CPnt3D*, CPnt3D*, CPnt3D*, CTexHandle*, float, CPnt3D*) | `lw a1,0(a0)`, `lui v1,0x1` / `and` (bit 16), `beq` → 0x2254c8 | T | Clear → the visual gets no decal. Set → a `CSubMesh` (vtype 2) is remembered in s6 for later; any other visual gets `CVisual::ApplyDecalRender` (0x2254c0) | N (`lw s0,140(s5)` 0x22546c, `lw a0,0(s0)` 0x225478) | new |

The only external caller of `SetApplyDecals` is `CClutter::Read` 0x218efc,
with b = 0. `ApplyDecal` callers are `CZMarkList::AddNewMark` and
`CZSealBody::HandleBloodDrip` / `HandleSealStep`. The plan's note "m_flag16:
use not proven" is contradicted.

### Plan bits with no outside site

Each of these is accessed only at its cited in-family sites:

- bit 3: ctor 0x30df94; VuUpdate 0x30aa0c; VuBatchProgram 0x30be60;
  VuBatchProgram_Decals 0x30ca1c.
- bit 4: ctor 0x30dfa8; VuUpdate 0x30abd8.
- bit 5: ctor 0x30dfbc; VuObjectSetup 0x30c3c8.
- bit 6: ctor 0x30dfd0; VuObjectSetup 0x30c3a8.
- bit 7: ctor 0x30dfe4.
- bit 9: ctor 0x30dff8.
- bit 10: Read 0x30d160.
- bit 15: ctor 0x30e020; VuUpdate 0x30abb8.
- bit 17: ctor 0x30e048; VuUpdate 0x30a9c4; VuBatchProgram 0x30be20.
- bit 18: ctor 0x30e05c.

No instruction anywhere in the ELF tests, masks or writes **bit 2, bit 12, or
bits 19–31** individually, and byte +3 is never accessed as a byte. These bits
are touched only by whole-word operations:

- ctor `sw zero,0(v0)` 0x30df44;
- `tag_VIS_PARAMS::operator=` `lwc1`/`swc1` 0x30f690/0x30f698;
- the 24-byte "vparams" Insert/Fetch (Write 0x30d118, Read 0x30d158).

The analyzer also reported sites where the "word +0" being touched is not a
visual. These were rejected:

- `CMeshDecal` nodes reached through `CMesh`+0x6c: 0x30ed8c, 0x30ed98,
  0x30f1a8, 0x30f1b4.
- list nodes and allocator headers: `__dl`, `list_imp`, `__sinit_*`,
  `CSealUnit`, `_free_r`.
- the `strcpy` result in `CMission::PreOpen`.
- the `CPnt3D*` t0 in the static `Destruction_Instance::Create`: 0x2367e4,
  0x2367ec.

### +0x8 and +0xa (m_unk08)

| Site | Function | Instruction | R/W | Value / use | Proof | Class |
|---|---|---|---|---|---|---|
| 0x30e08c | zdb::CVisual::__ct | `sh zero,8(v0)` | W | 0 | `this` | in-family (cited) |
| 0x30e094 | zdb::CVisual::__ct | `sh zero,10(v0)` | W | 0 | `this` | in-family (cited) |
| 0x30f6bc / 0x30f6c0 | zdb::tag_VIS_PARAMS::operator= | `lw v1,8(a1)` / `sw v1,8(a0)` | R/W | Word copy (only `CMesh::Clone`) | params | in-family (cited) |
| 0x30d118 / 0x30d158 | CVisual::Write / Read | "vparams" 24 bytes | R / W | Serialization | `this` | in-family |

There are no outside sites. No instruction anywhere reads +0x8 or +0xa for a
decision. The only other hits were the `CMeshDecal`, list and `CPnt3D` sites
rejected above.

### What the code shows

- **Bit 0:** Visuals created by `Particle::CreateVisuals` set it from texture
  `m_transparent` && !`m_bumpmap`. The CNode code (`AddVisual`, both `_Copy`
  paths) and `Destruction_Instance` turn it, with bit 8 clear, into the node's
  `m_transparent`.
- **Bit 1:** Combined with `CPipe::m_doFog`, it yields `CVisual::m_fogEnable`
  for that visual's draw.
- **Bit 8:** Particle visuals copy texture `m_bumpmap` into it. It only ever
  vetoes the bit-0 node mark.
- **Bit 11 (new):** Particle visuals set it from alpha-blended texture state.
  `RenderVisual` routes visuals that have it into the deferred, sorted `CAlpha`
  list (unless `m_simpletrans` or `m_doUI` is set).
- **Bit 13 (new):** Range-based bilinear adjustment. Within
  `m_adjustBilinearRange` the visual is deferred to `CAlpha` and drawn with
  `SetBilinear(…, 1)`; beyond it, `SetBilinear(…, 0)` is called.
- **Bit 14:** The multipass bit is also written by
  `CNode::SetApplyMultipassEffects`, recursively over the node tree. Clutter
  nodes clear it.
- **Bit 16:** The decal-enable bit. `CNode::ApplyDecal` skips visuals without
  it, and `CNode::SetApplyDecals` sets it recursively. Clutter nodes clear it.
- **Other bits:** Bits 3, 4, 5, 6, 7, 9, 10, 15, 17 and 18 add no uses beyond
  the plan. Bits 2, 12 and 19–31 are never accessed individually.
- **+0x8 / +0xa:** Only zeroed, copied and serialized. Nothing reads them for a
  decision.
## Correction (2026-10-23, struct layout of tag_ObjectHeader)
The earlier statement that VuObjectSetup sets 'object-header word 0' to 63 (m_render_mode == -2) or m_fovClipWord >> 8 is wrong: those stores (0x30c398/0x30c3a4) go through s0 = a1, the _word128 * VU program buffer at header+0x20; the tag_ObjectHeader is a2 (s2). The m_render_mode note in the CVisual type plan should say 'the first word of the VU program buffer'.

## Correction 2 (2026-10-23, tag_ObjectHeader planning)
The accepted zdb-cvisual plan's notes for m_global_light_enable and m_ambient_light_enable say VuObjectSetup writes 'object-header +4/+8'. Those stores (0x30c3c0-0x30c3e4) also go through s0 = a1, the VU program buffer, not the tag_ObjectHeader (a2 = s2). Notes only; no applied type is affected. Fix both notes (and the m_render_mode 'word 0' note) in the next CVisual plan revision.
