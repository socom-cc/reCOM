# zdb::CVisual static data members - recon repair 005 review table

Plan `build/recon-plans/socom-work-recon-repair-005.json` (item `socom:work:recon-repair-005`). Facts: `build/facts/cvisual-statics.txt` (`recon global-facts --qualifier zdb::CVisual`). Live name/type from read-only `audit_global` (2026-10-24).

Every row relabels the mangled primary symbol to its demangled qualified name (the mangled name is re-created as a label). Byte flags are `bool` (user decision 2026-10-24): 1-byte, every load lbu tested only against zero, stores 0/1; Metrowerks DWARF 1 encodes bool as fund_type 0x3, so the bytes alone cannot tell bool from unsigned char.

| # | address | current name | proposed label | current type | proposed type | evidence |
|---|---------|--------------|----------------|--------------|---------------|----------|
| 1 | 0x4753e8 | `m_customGlobalLightIdx__Q23zdb7CVisual` | `zdb::CVisual::m_customGlobalLightIdx` | `undefined4` | `int` | init -1; compared with -1, then cvt.s.w (signed word to float) at 0x30aca8 |
| 2 | 0x4753ec | `m_applyShadow__Q23zdb7CVisual` | `zdb::CVisual::m_applyShadow` | `undefined1` | `bool` | byte flag: lbu tested vs 0; sb 0 / xori 1 |
| 3 | 0x4753f0 | `m_applyLocalLights__Q23zdb7CVisual` | `zdb::CVisual::m_applyLocalLights` | `undefined1` | `bool` | byte flag: 8 lbu tested vs 0; sb 0/1, xori 1 |
| 4 | 0x4753f4 | `m_applyMultipass__Q23zdb7CVisual` | `zdb::CVisual::m_applyMultipass` | `undefined1` | `bool` | byte flag: lbu -> sltu !=0; sb 0/1 |
| 5 | 0x4753f8 | `m_fogEnable__Q23zdb7CVisual` | `zdb::CVisual::m_fogEnable` | `undefined1` | `bool` | byte flag: lbu tested vs 0 / andi 1; sb of sltu results and 0 |
| 6 | 0x4753fc | `m_lightingEnable__Q23zdb7CVisual` | `zdb::CVisual::m_lightingEnable` | `undefined1` | `bool` | byte flag: lbu tested vs 0 / andi 1; sb 0/1, sltu, !bool param (LandmarkEnable) |
| 7 | 0x475400 | `m_GlobalLightScale__Q23zdb7CVisual` | `zdb::CVisual::m_GlobalLightScale` | `undefined4` | `float` | swc1 of mul.s results (0x242ec0, 0x30acbc, 0x30c778); init 1.0f |
| 8 | 0x475404 | `m_AmbientLightScale__Q23zdb7CVisual` | `zdb::CVisual::m_AmbientLightScale` | `undefined4` | keep | keep: only an lwc1 copy into a packet (fpr-copy); 1.0f init is a bit pattern only |
| 9 | 0x4765dc | `m_primAlpha__Q23zdb7CVisual` | `zdb::CVisual::m_primAlpha` | (no data) | keep | keep: only sw of the zero-extended bool param of AlphaEnable; never loaded, sign unproven |
| 10 | 0x4765e0 | `m_sprEndOfMP__Q23zdb7CVisual` | `zdb::CVisual::m_sprEndOfMP` | (no data) | `_word128 *` | VuBatchProgram's _word128 * result + 0x280; sltu-compared with the _word128 * packet param + k |
| 11 | 0x4765e4 | `m_landmarkFlag__Q23zdb7CVisual` | `zdb::CVisual::m_landmarkFlag` | (no data) | `bool` | byte flag: lbu tested vs 0; sb of LandmarkEnable's bool param |
| 12 | 0x4765e8 | `m_renderMap__Q23zdb7CVisual` | `zdb::CVisual::m_renderMap` | (no data) | `bool` | byte flag: lbu tested vs 0; sb 0/1 |
| 13 | 0x4765ec | `m_applyScaleColor__Q23zdb7CVisual` | `zdb::CVisual::m_applyScaleColor` | `uchar` | `bool` | byte flag: lbu tested vs 0; sb 0/1; replaces the uchar of accepted group 54ec3eaac02eb846ef5a |
| 14 | 0x4765f0 | `m_applyDetailTexture__Q23zdb7CVisual` | `zdb::CVisual::m_applyDetailTexture` | (no data) | `bool` | byte flag: lbu tested vs 0; sb 0/1 |
| 15 | 0x4765f4 | `m_dmaChain__Q23zdb7CVisual` | `zdb::CVisual::m_dmaChain` | (no data) | `_word128 *` | passed (+index) in a1 to CSPR::Copy(_word128 *, _word128 *, int) x4 |
| 16 | 0x4765f8 | `m_dmaQwc__Q23zdb7CVisual` | `zdb::CVisual::m_dmaQwc` | (no data) | keep | keep: count stored from lhu fields, loaded into locals / tested vs 0; sign unproven |
| 17 | 0x4765fc | `m_opacity__Q23zdb7CVisual` | `zdb::CVisual::m_opacity` | (no data) | `float` | stored from VuUpdate's mangled float param (f12); lwc1 -> c.le.s/c.lt.s |
| 18 | 0x476600 | `m_rangeSqdToCamera__Q23zdb7CVisual` | `zdb::CVisual::m_rangeSqdToCamera` | (no data) | `float` | stored from CCamera::GetScaledRangeSquared f0; lwc1 -> c.le.s x3 |
| 19 | 0x476608 | `m_mtl_band__Q23zdb7CVisual` | `zdb::CVisual::m_mtl_band` | (no data) | keep | keep: only sw zero; never read |
| 20 | 0x47660c | `m_local_light_cnt__Q23zdb7CVisual` | `zdb::CVisual::m_local_light_cnt` | (no data) | keep | keep: count (0, ++, sltiu 10, sll index); sign unproven |
| 21 | 0x476614 | `m_specMapCnt__Q23zdb7CVisual` | `zdb::CVisual::m_specMapCnt` | (no data) | keep | keep: stored 0, read once as != 0; sign unproven |
| 22 | 0x476618 | `m_specMapGlobal__Q23zdb7CVisual` | `zdb::CVisual::m_specMapGlobal` | (no data) | `bool` | byte flag: lbu -> sltu !=0; sb 0 |
| 23 | 0x476620 | `m_lightMapCnt__Q23zdb7CVisual` | `zdb::CVisual::m_lightMapCnt` | (no data) | keep | keep: count = 0 or m_lightMapList size word; tested vs 0 / copied to packets; sign unproven |
| 24 | 0x476624 | `m_shadowMapCnt__Q23zdb7CVisual` | `zdb::CVisual::m_shadowMapCnt` | (no data) | keep | keep: count = 0 or m_shadowMapList size word; tested vs 0 / sltu; sign unproven |
| 25 | 0x476630 | `m_fovClipWord__Q23zdb7CVisual` | `zdb::CVisual::m_fovClipWord` | (no data) | `uint` | &global passed in a2 to CCamera::TestFOV(PNT4D *, unsigned int *, bool); load srl 8 |
| 26 | 0x476634 | `m_ModelToWorld__Q23zdb7CVisual` | `zdb::CVisual::m_ModelToWorld` | (no data) | `CMatrix *` | passed in a1 to Vu0MatrixInverseWithUniformScale(CMatrix *, CMatrix *); lqc2 x4 deref; stored from NodeSetup's CMatrix * param |
| 27 | 0x476638 | `m_fovStatus__Q23zdb7CVisual` | `zdb::CVisual::m_fovStatus` | (no data) | keep | keep (doubtful): only store is NodeSetup's mangled int param; loads tested vs 0; int vs unsigned unproven |
| 28 | 0x47663c | `m_adjustBilinearRange__Q23zdb7CVisual` | `zdb::CVisual::m_adjustBilinearRange` | (no data) | `float` | lwc1 -> c.le.s / c.lt.s (0x2426ac, 0x2426f0) |
| 29 | 0x476640 | `m_dmaSubfaceChain__Q23zdb7CVisual` | `zdb::CVisual::m_dmaSubfaceChain` | (no data) | `_word128 *` | passed (+index) in a1 to CSPR::Copy as _word128 *; = m_dmaChain + offset |
| 30 | 0x476644 | `m_dmaSubfaceQwc__Q23zdb7CVisual` | `zdb::CVisual::m_dmaSubfaceQwc` | (no data) | keep | keep: count stored from an lhu field; tested vs 0 / copied to a local; sign unproven |
| 31 | 0x511580 | `m_customGlobalLight__Q23zdb7CVisual` | `zdb::CVisual::m_customGlobalLight` | (no data) | keep | keep: __construct_array(.., tag_GlobalLight ctor, 128, 4) => zdb::tag_GlobalLight[4], but no such live/DWARF type |
| 32 | 0x511790 | `m_stack_vid__Q23zdb7CVisual` | `zdb::CVisual::m_stack_vid` | (no data) | keep | keep: dtor = std::stack<Ui, std::deque<Ui,...>>; no live type, ',' unspellable (issue d73db800) |
| 33 | 0x5117c0 | `localLightBuf__Q23zdb7CVisual` | `zdb::CVisual::localLightBuf` | (no data) | `CPnt4D[20]` | __construct_array(.., CPnt4D::CPnt4D, 16, 20) = 320 bytes |
| 34 | 0x511900 | `localLightPtr__Q23zdb7CVisual` | `zdb::CVisual::localLightPtr` | (no data) | `CLight *[10]` | AddLocalLight (static) stores its CLight * param at [cnt*4]; 40 = 10 ptrs; cnt < 10 |
| 35 | 0x511928 | `m_scaleColor__Q23zdb7CVisual` | `zdb::CVisual::m_scaleColor` | (no data) | keep | keep: PNT3D::operator= receiver, but CPnt3D derives from PNT3D (DWARF CPnt4D sibling m_basefog_color takes PNT4D::operator= too) |
| 36 | 0x511938 | `m_addColor__Q23zdb7CVisual` | `zdb::CVisual::m_addColor` | (no data) | keep | keep: three 4-byte words, no typed receiver/param: PNT3D, CPnt3D, float[3] all fit |
| 37 | 0x511958 | `m_specMapList__Q23zdb7CVisual` | `zdb::CVisual::m_specMapList` | (no data) | `CLightMapVector` | registered with CLightMapVector's dtor; __vector_pod<Ui> base receiver; 12 bytes |
| 38 | 0x511978 | `m_lightMapList__Q23zdb7CVisual` | `zdb::CVisual::m_lightMapList` | (no data) | `CLightMapVector` | CLightMapVector dtor + CLightMapVector::Exists receiver; __vector_pod<Ui> base calls |
| 39 | 0x511998 | `m_shadowMapList__Q23zdb7CVisual` | `zdb::CVisual::m_shadowMapList` | (no data) | `CLightMapVector` | CLightMapVector dtor + CLightMapVector::Exists receiver; __vector_pod<Ui> base calls |
| 40 | 0x5119b8 | `m_projectedMapList__Q23zdb7CVisual` | `zdb::CVisual::m_projectedMapList` | (no data) | keep | keep: dtor = zdb::CProjectedMapVector, no such live/DWARF type |
| 41 | 0x5119d0 | `m_WorldToModel__Q23zdb7CVisual` | `zdb::CVisual::m_WorldToModel` | (no data) | `CMatrix` | &global passed in a0 to Vu0MatrixInverseWithUniformScale(CMatrix *, ...); lqc2 x24 at +0/10/20/30; unit-matrix init |

Totals: 41 globals, 26 typed, 15 keep (label only).

Excluded (DWARF `global_variable` records; stage 2 named and typed them): 0x4765d8 m_camera, 0x476604 m_basefog_near, 0x476610 m_specMapTexture, 0x47661c m_lightMapTexture, 0x476628 m_envFrontMapTexture, 0x47662c m_envBackMapTexture, 0x5117b0 m_basefog_color.
