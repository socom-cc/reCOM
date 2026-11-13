# boot-decals notes (2026-11-12, socom-port-decals)

Scratch for decals (bullet holes, blood, footprints). Untracked. Changed files: `mine.txt`.

## Tools (this folder)
Copied from boot-fx (paths fixed to boot-decals / tree-decals); use as in boot-fx/NOTES.md. New:
- `go.ps1 <build> <name> [seconds] [shots]`: copy the WSL build's ELF here and boot it through
  `tools/pcsx2-boot.ps1` (log `<name>.log`, shots `<name>-<t>.png`).
- `zoom.py <png> x0 y0 x1 y1 [scale]`: crop + upscale a screenshot region.
- `sizes.sh` + `lay/sizes.cpp`: static_asserts on the decal record layouts (all pass).
- `asm/*.txt`: disassembly of every function below.
- Pads: `pad_g2.txt` (= fx e2 start; fire at the ground, run forward at 1035, turn back at 1230,
  second burst 1330-1372), `pad_g1.txt`, `pad_none.txt` (empty = default build through bd.sh).
- Test-only edits (test tree): `diag_a1.txt`, `edits/t_apply.txt` (traces), `edits/t_pool.txt`
  (temp pool 20+25 so the recycle path runs).
- `edits/*.rep.txt`, `edits/*.py`: the edits as applied to the repo (kept for reference).

## How the ELF does decals (no DWARF for any zdb visual/decal type; all from the asm)
- A decal is one triangle of a visual drawn again with the decal texture. `CDecal` is a 272-byte
  POD record (not a CVisual): list link, owner visual, instance id, the texture's VU select tag
  (`CTexture::m_dmaRefVu`) and a DMA REF to its own 14-qword VIF packet: a one-triangle batch in
  the normal batch layout with float vertices. `CVisual::VuUpdate` appends, after the instance
  chain, one packet with `VuBatchProgram_Decals` (vuColorToFloat0 = command 70 instead of
  vuDecompress) and then per decal its select tag (when the texture changes) + its REF.
  **No VU1 program is missing**: command 70 is in the port's zrndr_vu1.vsm (byte-equal to the ELF).
- Placement: `CZMarkList::AddNewMark` (impacts) / `HandleSealStep` (footsteps) ->
  `CNode::ApplyDecal` (world-to-UV matrix from position, projection direction, size, texture
  width) -> `CVisual::ApplyDecalRender` (into model space) -> `CVisual::ApplyDecal`: walks the
  instance chain with `CVisData`, takes every triangle facing against the incoming direction
  whose corners fall on the unit UV square within 5 units of the decal plane ->
  `AttachDecal` -> `CDecal::AddDecal`.
- Pools: `CDecalPool` {out count, BASE, OVERFLOW, recycle count, RTArray<CDecal>*}. A decal taken
  while more than BASE are out bumps the recycle count; `RecycleTick` (CPipe::RenderWorld, each
  frame) takes the oldest in-use decals back. Sizes from decals.rdr: m8 TEMP 300+50, PERM 30+0.
- Mission data (decals.rdr, already loaded as `theMission.m_decalsRdr`): `DECAL_SETS` (m8:
  GRENADE_BLAST permanent, BULLET_MARK_SMALL; per material a texture + size range) -> the weapon's
  `m_decalset`; `BLOOD_DECALS` (3 stamps); `FOOTSTEP_DECALS` (seal_env, fx worker);
  `TEMP_/PERM_DECAL_POOL`. `WEAPON_DECALS` is read but never stored (ELF quirk below).

## Written (ELF addresses)
- zVisual: CDecal::AddDecal 0x312e80, Tick 0x312e70, PutTempDecal 0x313320, PutPermDecal
  0x3132f0; CDecalPool Init 0x313460 / Get 0x3133e0 / RecycleTick 0x313360; CMeshDecalPool Init
  0x313280 / Uninit 0x312de0 / RecycleTick 0x313190; CMeshDecal FreeMem 0x312e20 / PutTempDecal
  0x313240; UVCompare 0x3134d0; CVisData Clear 0x310a30 / SelectVertex 0x3109a0 / SearchVertex
  0x3107b0 / NextVertex 0x310560 / SetBilinear 0x310650; CVisual ApplyDecal 0x3096e0 /
  ApplyDecalRender 0x309500 / AttachDecal 0x3093c0 / RemoveDecal 0x309360 / DereferenceDecals
  0x3092b0 / VuBatchProgram_Decals 0x30c9c0, the decal part of VuUpdate 0x30b4c8-0x30b6f8;
  CalcWorldToUV 0x30cc50 and 0x30ce20; CMesh RemoveMeshDecal 0x30ede0 / DereferenceDecals 0x30ed60.
- rt: RTArray<T> destructor (0x31f980, 0x3139a0) and GetOldestUsed (0x313660, 0x3138d0).
- zNode: CNode ApplyDecal 0x2253a0 / RemoveDecals 0x2251d0 / SetApplyDecals 0x225a10;
  CWorld::RemoveDecals 0x22dc50.
- zWeapon: CZWeapon CreateMarkList 0x31f530 / DestroyMarkList 0x31f440 / OpenDecals 0x31cbb0;
  CZMarkList Init 0x31de10 / UnInit 0x31dd10 / ReadDecalNames 0x31dae0 / ReadWeaponDecals
  0x31d960 / ReadBloodDecals 0x31d800 / AddNewMark 0x31d360; CZDecalSet ReadDecalSet 0x31cf50 /
  ReadDecalEntry 0x31cd90 / DestroyDecalSet 0x31d1e0.
- zFTS: CMission::Open now runs `m_pMarklist->Init()` (0x1f8410).
- compat: sceVu0TransMatrix 0x152498, sceVu0CameraMatrix 0x152850.
- Types (zvis.h, vis_vector.h, zweapon.h): CDecal, CMeshDecal, AddonPoint, CVisData (96 bytes),
  CDecalPool/CMeshDecalPool (were std::vector placeholders), CZDecalDef, CZMarkList members
  (DWARF), VU1_COLOR_TO_FLOAT0. Member names of the no-DWARF types are invented (flagged).
  Signature fixes: CVisual::ApplyDecal is a member (was static; the ApplyDecal(CDecal*)
  declaration with no symbol is gone), UVCompare returns bool, CDecalPool::Get returns the
  decal, CVisData Select/Search/NextVertex return the cursor, CZDecalSet::DestroyDecalSet is
  static bool, CZMarkList::ReadDecalNames returns bool.

## Root cause found on the way
- Footprints got 0 triangles: `projDirDown` (0x508cd8) is (0, -1, 0), stored by
  `__sinit_seal_env.cpp` (0x46d1c0); the port had it as zeroed `int[3]`, so the facing test never
  passed. Fix is in the shared file seal_env.cpp: **edit file `edits/se01.txt`** (not applied to
  the repo: the file has another worker's uncommitted changes).

## Results (m8, fake pad)
- b1.log (pad_g2, real pool sizes, 153 s = 100 s in mission): 2 sets, 3 blood decals, pools
  300+50 / 30+0; 91 decals out, 300 frames every 5.005 s before and after (no slowdown), no
  exception. Bullet marks on snow, blood stamps on the snow behind a hit enemy, 22 footsteps
  each with 1-3 triangles. Screens: b1-88.png (+_z), a2-77.png (+_z), b1-95_z.png, b1-150.png.
- a3.log (test pool 20+25): out count holds at 20, every extra decal sets recycle 1 and the next
  frame takes the oldest back (86 attached over the run); a3-98.png shows only the newest left.
- default.log/png: build without hooks or fake pad boots to the main menu.
- Only snow ground was hit in these runs; walls/wood/metal use the same path with other set
  entries (not exercised).

## ELF quirks kept
- CVisual::ApplyDecal writes the second corner's vertex normal into the third corner's record,
  so the second vertex of every decal is lit with the stale (zero) normal.
- Only triangles whose three corners are within 5 units of the decal plane take a decal: on
  large sloped terrain triangles some footprints/marks are skipped.
- ReadWeaponDecals clears the names before the material lookup (NULL name -> index 0): the
  WEAPON_DECALS tables are never filled; marks come only from the weapons' decal sets.
- CDecalPool::RecycleTick uses the caller's recycle counter but always CDecal::m_tempPool's
  array; CZMarkList::UnInit leaves the CDecal pools' array pointers dangling.
- CVisData: a batch that starts before the wanted index is skipped; the first vertex of a batch
  is record 0 whatever its index entry.
- Characters: submesh visuals (vtype 2) stop CNode::ApplyDecal; the ELF never takes a
  CMeshDecal from its pools (no RTArray<CMeshDecal>::GetNext), so bodies get no decals.
- m_farBloodDecals is never filled; m8 has no "bullet_mark" model (the 40 mark nodes are skipped).

## Port deviations
- CalcWorldToUV (2-point form): the ELF leaves two components of the "least axis" stack vector
  uninitialised; the port zeroes them.
- Guards (flagged `port: guard`): CVisual::ApplyDecal returns 0 for an instance without chain or
  decal slot; a decal-set/blood texture that is not found is not added to the world's texture
  lists; the existing `m_stack_vid.back() < m_decals.size()` guard in VuUpdate is kept.
- vis_main.cpp gets a file-local `decalps` table (ELF 0x43b530 has no skeleton stub).
- Traces kept in src (SOCOM_PORT only): "DECAL: set ..." per set and "DECAL: pools ...".

## Not written / next
- CMission::Close / ReOpen_Unload1 are stubs: they must call CWorld::RemoveDecals (0x1f71c0,
  0x1f7d00) and CZDecalSet::DestroyDecalSet (0x1f740c); CCoreState::auxUnload (stub) calls
  CZMarkList::UnInit. Until then a second mission load re-reads the sets (duplicates, first
  match wins) and re-creates the pools without returning the old decals.
- CZProjectile::HandleDetonateExplosion (0x317cd0; calls AddNewMark at 0x317d2c): grenade blast
  marks (GRENADE_BLAST set, permanent pool). CZSealBody::HandleBloodDrip (0x2919a0) and the
  BLOOD_DRIP_DECALS part of InitDecalHandles. CVisData::ReplaceTextureData 0x310700 (stub).
- zrndr_pipe.cpp ~l.207 comment still says the decal textures are not written (not my file).
