# Stage 2: gamez/zNode (2026-11-26)

The one list of `gamez/zNode` (list a): the owner files node_io.cpp, node_vector.cpp, node_main.cpp,
node_model.cpp, node_saveload.cpp, node_projectedmap.cpp, node_shadow.cpp, node_util.cpp,
node_world.cpp, node_assetlib.cpp, node_lensflare.cpp and node_wave.cpp (release 0x226a70-0x235810,
and 0x32d390-0x32d530). It holds 14 uncertain rows (6 removed, 5 new, 2 unsure, 1 weak pair
(`slot-only`); none flagged `identical-copy`), 15 sampled deviating rows out of 80, and 137 exact
rows that were not checked one by one. Pairing produced by `socom-release-compare-c1`
(`python tools/release/compare.py`); checked by `socom-release-check-ai-node`, who did not write the
tool, at HEAD 293696c3. The check sheet (`compare.py --sheet gamez/zNode --list a`) was the starting
point. Both images were decoded with the release tools; callers were found by scanning both images
for `jal`/`j`, `lui`/`addiu` address loads, vtable slots and data words. Ghidra was not needed.

As the guard on the committed pairs, all 220 paired rows of the zNode owner files had their callers,
address loaders, vtable slots and data-word counts compared with the prototype's through the map,
and their own ordered calls and loads compared for substitutions. The ordered calls of every paired
caller (372) of a zNode function were compared too. The 9 vtables with a slot in these files were
aligned slot by slot. Each of the 34 paired rows with a byte twin on either side was scored by the
callers it shares with its counterpart.

What settled rows, in the order it was used: the call site in a paired caller (StartEngine,
TickZAnimCmd, the DeleteTextureAssetCharacter wrappers, CVisual::ApplyDecal, TickExplosives and
zAnimObjectMotionTick); masked bytes equal up to the CWorld offsets; vtable slots; the slot between
paired neighbours.

## Checked rows

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| - | 0x224210 `_Write__Q23zdb6CLightFRQ23zdb9CSaveLoad` | removed | confirmed | slot 14 is gone from the CLightMap, CLight and CRenderMap tables (15 → 14 slots), like the zVisual Writes; no release caller |
| - | 0x225e80 `SetDynamicMotion__Q23zdb5CNodeFbb` | removed | confirmed | its only caller was SetDynamicLight's child loop: the prototype SetDynamicLight (bit 2 of +0x5c) recursed into SetDynamicMotion (bit 1). The release SetDynamicLight (the same 304 bytes) recurses into itself, which leaves SetDynamicMotion without callers. A prototype quirk the release no longer has |
| - | 0x2270e0 `SetScale__Q23zdb5CNodeFf` | removed | corrected to 0x22a630 | see the row below |
| 0x22a630 | - | new, owner guess | corrected to 0x2270e0 `SetScale__Q23zdb5CNodeFf` | same caller TickZAnimCmd (HandlePad and new 0x3a1ae0 added). Same slot, after SetScale(CPnt3D*). It writes the scale to +0, +0x14 and +0x28 and sets bit 1 of the flags at +0x9a (now a halfword); the virtual call through +0x94 slot 4 is gone, so the body is 28 bytes instead of 88 |
| - | 0x22c1a0 `GetClosestNode__Q23zdb5CNodeFPC6CPnt3DPC6CPnt3Dffff` | removed | confirmed | its callers no longer call it: TickMPBomb (now 372 bytes) dropped the node search, and TickPickups uses SubXZ distance tests instead |
| - | 0x22dfa0 `FindTextureAssetCharacter__Q23zdb6CWorldFPQ23zdb5CNode` | removed | confirmed | its only caller, the CNode destructor, dropped the call |
| 0x231050 | 0x22e070 `DeleteTextureAssetCharacter__Q23zdb6CWorldFPQ23zdb9CAssetLibPQ23zdb5CNode` | unsure, position, caller-mismatch | confirmed (deviating) | the same body: the list walk, remove_if, doDelBuffer on m_texmanager, the vector destructor and delete. Only the CNodeVector::Remove is gone; it moved into the two wrapper overloads, which no longer call this function. It is now called from CPipe::RenderWorld, so the texture is freed later |
| 0x231930 | - | new, owner guess | confirmed | CWorld method: the brightness at a point. It starts from the ambient colour (+0x660), adds the directional terms (+0x630 ...), then the point lights of the grid cell under the point (new zGrid 0x218e00, list at +192), attenuated by distance and radius (+0xc0, +0xc8, colour +0xd8). It returns a weighted sum of the three channels. Caller new seal sensor 0x2c0cc0 (twice) |
| 0x231f00 | - | new, owner guess | confirmed | GetAltitude with a bool: the body of GetAltitude (0x231e80) between a set and a restore of bit 1 of the intersect's flags byte (+2). Callers zAnimObjectMotionTick and ftsGetAltitudeApprox, which called GetAltitude in the prototype |
| 0x232050 | - | new, owner guess | corrected to 0x22eb70 `GetIntersect__Q23zdb6CWorldFPC6CPnt3DPC6CPnt3D` | the masked bytes of the prototype GetIntersect, except the CWorld offsets (+0xcc → +0xdc, 1648 → 1664, as in the paired GetAltitude). 7 of the prototype's 8 callers call it (TickExplosives, OKToStand, OKToJump, OKToPeek, PostComputeNextPosition, CAiSDeploy::Tick, TickFlashlight) |
| 0x235620 | - | new, owner guess | confirmed | the zVisual check's claim holds: a 52-byte MMI/VU0 helper that unpacks a vertex's three s16 coordinates (`lq`, MMI widen and shift, `qmtc2`, a VU0 int-to-float), combines them with the record at a1 (the walk's +0x18, from which the prototype read the offsets) and stores a quadword. CVisual::ApplyDecal calls it three times. At those places the prototype converted each coordinate inline in scalar FPU code (`lh`, `cvt.s.w`, divide, add); not VU0 code |
| 0x235690 | 0x232080 `Init__Q23zdb7CRippleFv` | deviating (weak), slot-only | confirmed | the same call site: the second call of StartEngine, before CTextureFX::Init. The release body is empty (`jr ra`): the ripple pool is no longer created |
| - | 0x232170 `__ct__22RTPool<Q23zdb7CRipple>FUi` | removed | confirmed | its only caller CRipple::Init is empty now |
| 0x32d390 | 0x2322c0 `resize__Q23std38__list_imp<PCv,Q23std14allocator<PCv>>FUiRCPCv` | unsure, call, low-similarity, moved | confirmed (deviating) | the only resize instance on both sides. Shared caller: the RTPool<CTextureFX> constructor; its other prototype caller, the RTPool<CRipple> constructor, is removed. Its erase is now inline (unlink and delete), hence the low similarity |

Sampled deviating rows (same function on both sides):

| release | prototype | verdict | basis |
|---|---|---|---|
| 0x226c80 | 0x223390 `Read__Q23zdb6CLightFRQ23zdb9CSaveLoad` | yes | slot 10 of the CLightMap, CLight and CRenderMap tables |
| 0x228030 | 0x2248a0 `SetModelname__Q23zdb5CNodeFPCc` | yes | the same four callers |
| 0x229c50 | 0x2266d0 `SetName__Q23zdb5CNodeFPCc` | yes | 32 shared callers (Particle::Source's call moved into new 0x23e1a0) |
| 0x22a680 | 0x2271a0 `SetRotation__Q23zdb5CNodeFRC5CQuat` | yes | 13 shared callers |
| 0x22a710 | 0x227270 `SetMatrix__Q23zdb5CNodeFPC7CMatrix` | yes | 19 shared callers |
| 0x22aac0 | 0x227650 `DeleteChild__Q23zdb5CNodeFPQ23zdb5CNode` | yes | slot 5 of the eight CNode-family tables |
| 0x22af70 | 0x227b40 `AddVisual__Q23zdb5CNodeFPQ23zdb7CVisual` | yes | the same four callers |
| 0x22df80 | 0x22ac50 `LoadAssetLib_PS2__Q23zdb9CSaveLoad...` | yes | same caller LoadAssetLib |
| 0x230cc0 | 0x22dc50 `RemoveDecals__Q23zdb6CWorldFv` | yes | the same three callers |
| 0x230f30 | 0x22de80 `WipeoutTextureAssetCharacters__Q23zdb6CWorldFv` | yes | same caller ReOpen_Unload1 |
| 0x231280 | 0x22e240 `DeleteTextureAssetCharacter__Q23zdb6CWorldFPcPQ23zdb5CNode` | yes | same caller, the CZSealBody destructor |
| 0x231e80 | 0x22ea80 `GetAltitude__Q23zdb6CWorldFPC6CPnt3Df` | yes | masked bytes equal except the CWorld offsets; three shared callers (three moved to the bool overload 0x231f00 or dropped it) |
| 0x232190 | 0x22ebf0 `FindLandmark__Q23zdb6CWorldFPCc` | yes | slot 16 of the CWorld table |
| 0x232320 | 0x22ed80 `GenerateLightList__Q23zdb6CWorldFv` | yes | same caller LoadWorld |
| 0x233d70 | 0x2307a0 `GetLoadedLibRef__Q23zdb9CAssetMgrFPCc` | yes | the same five callers |

Found by the cross-check, outside the list's rows:

| release | prototype | tool | verdict | reason |
|---|---|---|---|---|
| 0x2320d0 | 0x22eb70 `GetIntersect__Q23zdb6CWorldFPC6CPnt3DPC6CPnt3D` | deviating, call-deviating, call-and-slot (similarity 0.231) | corrected to new | a new overload with a bool (a3): the GetIntersect body between a set and a restore of bit 0 of the intersect's flags byte (+2), as 0x231f00 does for GetAltitude. Its one caller, zAnimObjectMotionTick, is the only prototype caller of GetIntersect that switched to it; the real GetIntersect is 0x232050 (above) |

## Settled pairs (tool input)

In the format of `settled-pairs.tsv`; that file is not edited here.

| release | prototype | basis | checker | date | owner | flags |
|---|---|---|---|---|---|---|
| 0x22a630 | 0x2270e0 | same caller TickZAnimCmd; slot after SetScale(CPnt3D*); writes the scale to +0/+0x14/+0x28 and sets bit 1 of +0x9a | socom-release-check-ai-node | 2026-11-26 | | |
| 0x232050 | 0x22eb70 | masked bytes of GetIntersect except the CWorld offsets (+0xcc → +0xdc, 1648 → 1664); 7 of its 8 prototype callers | socom-release-check-ai-node | 2026-11-26 | | |
| 0x2320d0 | new | the bool overload of GetIntersect (sets and restores bit 0 of the intersect flags); only caller zAnimObjectMotionTick | socom-release-check-ai-node | 2026-11-26 | src/gamez/zNode/node_world.cpp | |
| 0x231050 | 0x22e070 | same body minus CNodeVector::Remove, which moved into its two former callers; now called from CPipe::RenderWorld | socom-release-check-ai-node | 2026-11-26 | | |
| 0x32d390 | 0x2322c0 | the only list_imp<PCv>::resize on both sides; shared caller RTPool<CTextureFX>'s constructor; erase inlined | socom-release-check-ai-node | 2026-11-26 | src/gamez/zVisual/vis_texfx.cpp | |
| 0x235690 | 0x232080 | the same call site in StartEngine (second call, before CTextureFX::Init); body now empty | socom-release-check-ai-node | 2026-11-26 | | |
| 0x32d470 | 0x232340 | owner: list_imp<PCv>::insert now follows the RTPool<CTextureFX> instances; node_wave.cpp no longer instantiates RTPool<CRipple>'s constructor | socom-release-check-ai-node | 2026-11-26 | src/gamez/zVisual/vis_texfx.cpp | |
| 0x32d530 | 0x2324c0 | owner: list_imp<PCv>::init, the same | socom-release-check-ai-node | 2026-11-26 | src/gamez/zVisual/vis_texfx.cpp | |

Rows that change together: 0x22a630 and the removed 0x2270e0 (one row once paired); 0x232050 and
0x2320d0 (the counterpart moves from the second to the first).

## New and removed

New in the list (names are guesses unless the basis says otherwise):

| release | what it does | proposed name (basis) |
|---|---|---|
| 0x231930 | brightness at a point (ambient, directional and the cell's point lights) | guess: `GetLightLevel__Q23zdb6CWorldFPC6CPnt3DUif` (arguments: point, flags, radius) |
| 0x231f00 | GetAltitude with the intersect's flag bit 1 set or cleared for the call | guess: `GetAltitude__Q23zdb6CWorldFPC6CPnt3Dfb` |
| 0x2320d0 | GetIntersect with the intersect's flag bit 0 set or cleared for the call | guess: `GetIntersect__Q23zdb6CWorldFPC6CPnt3DPC6CPnt3Db` |
| 0x235620 | unpacks and offsets one compressed vertex on VU0 | guess: a header inline of the CVisData vertex format (its only caller is in vis_main.cpp); the owner node_wave.cpp is by position only |

Not new, though the map has them as new: 0x22a630 (`SetScale__Q23zdb5CNodeFf`) and 0x232050
(`GetIntersect__Q23zdb6CWorldFPC6CPnt3DPC6CPnt3D`).

Really removed:

- CLight::_Write: the vtable slot is gone (no ZAR writer, as in zVisual).
- CNode::SetDynamicMotion: only reached through SetDynamicLight's child loop, which now recurses into
  SetDynamicLight.
- CNode::GetClosestNode, CWorld::FindTextureAssetCharacter: their callers dropped the calls.
- RTPool<CRipple>'s constructor: CRipple::Init is empty.
- Not removed, though the map has it: SetScale(float) (0x22a630).

The open point from the zVisual check is settled: 0x235620 is a VU0 helper that CVisual::ApplyDecal
calls three times (the prototype did that work inline, in scalar FPU code). CNode::ApplyDecal no
longer skips visuals of type 2 (CSubMesh): the prototype only remembered them, the release calls new
0x3264b0 with the sub-mesh's mesh (+0x6c) and matrix id (+0x68). As before, it does not walk the
children once such a visual was seen.

Layouts, plainly shown by settled rows: CWorld's intersect pointer moved from +0xcc to +0xdc and its
grid from +0x670 to +0x680 (GetAltitude, GetIntersect); CNode's flags at +0x9a are written as a
halfword.

## Still unsure

None of the list's rows. Open points:

- The names of the new functions are guesses.
- 0x235620's owner is by position only (between CRipple::Tick and CRipple::Uninit).

## How the tool did

| class | rows | right | wrong |
|---|---|---|---|
| removed | 6 | 5 | 1: SetScale(float) is 0x22a630 |
| new | 5 | 3 | 2: 0x22a630 is SetScale(float), 0x232050 is GetIntersect |
| unsure | 2 | 2 (the candidates were right) | 0 |
| deviating (weak), slot-only | 1 | 1 | 0 |

The sample: 15 of 15 deviating rows are the same function on both sides.

The cross-check: 220 paired rows compared (callers, address loaders, vtable slots, data words,
ordered calls), the ordered calls of 372 paired callers, 9 vtables slot by slot, 34 rows with byte
twins scored by shared callers. Differences looked at: 31 caller sets, 34 caller call sequences, 7 call-order substitutions,
3 vtables, 12 twin ties. They are callers added, moved or dropped in the release (the Particle::Source
constructor's node set-up into new 0x23e1a0, HandleSealStep's decal call into new 0x29ddb0, zSeal
code), the removed _Write slot, the remove step moved out of DeleteTextureAssetCharacter, inlined
list code (Read, LoadAssetLib, CRenderMap) and double-precision math dropped from the CRenderMap
constructor. The twin ties are decided by vtable slot (SetActive, ReserveChildren, UpdateBBox) or by
the call position in the shared caller (CRipple::Init and CWorld::Init in StartEngine).
Pairs wrong: 1 (0x2320d0 is not GetIntersect; it is the new bool overload).

What misled it:

- GetIntersect: the release added a bool overload right after the original, and its one caller,
  zAnimObjectMotionTick, had called the original. The tool committed that low-similarity pair
  (0.231) on the shared caller and the slot, and left the original, whose masked bytes and seven
  callers match, as new.
- SetScale(float): the release body lost its virtual notification and is 28 bytes instead of 88, so
  the similarity was low. The caller and the slot decide.

What cost the most time: telling the new flag overloads of GetAltitude and GetIntersect from the
originals. Suggestion:

- Before committing a low-similarity pair on callers and slot, look for a new function with the
  masked bytes of the prototype side up to immediates (`imm-only`); prefer it.
