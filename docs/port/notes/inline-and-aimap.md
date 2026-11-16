# Inline functions into their headers; the old AI map formats (functional port)

Worker `socom-port-inline`, 2026-11-16, on HEAD d416f09d. Two tasks: the user-placed Metrowerks
binding-13 inline functions (`docs/reconstruction/decisions/stage4-function-placements.md`) moved
into their headers, and every AI map version the ELF reads written from the ELF. No
`@socom-anchor`, `@socom-artifact` or `@socom-skeleton` marker or generated block was added, moved
or changed (the stage 4 amendment regenerates them).

## Task 1: inline functions

Each body was compared with the ELF function instruction by instruction.

| ELF | function | verdict |
| --- | --- | --- |
| 0x223170 | `CMatrix::operator const float (&)[4][4]() const` | added: declared in the class (zmath.h, through a member typedef `rows_t`: a conversion function cannot spell an array type) and defined in `zmath_matrix.h` (`jr ra / move v0,a0`: the rows). Its two ELF callers now use it: `CNode::ComputeFacadeMatrix` (0x229734, node_model.cpp) and `CLensFlareSaturate::Tick` (0x3bda04, hud_lensflare.cpp) copy the product matrix through it into a temporary, then into the target (two `sceVu0CopyMatrix`, as the ELF; was one copy) |
| 0x1eb350 | `CMatrix::Transform(CPnt3D *, int) const` | moved zmath.h class -> `zmath_matrix.h` (`inline` after the class; zmath.h includes zmath_matrix.h at its end). The zmath_holding.cpp copy is a fenced `#if 0` non-const function the ELF lacks (left alone). **Fixed:** the ELF tests the count after the first point (do-while; count 0 runs on), the port tested it first |
| 0x1f5ef0 | `CMatrix::Transform(const CPnt3D *, CPnt3D *, int) const` | as above (moved, do-while fix) |
| 0x218de0 | `CMatrix::Multiply(const CMatrix *, CMatrix *) const` | moved zmath.h -> zmath_matrix.h; same as the ELF |
| 0x201650 | `CPnt3D::Cross(const CPnt3D *, CPnt3D *, bool) const` | already in zmath.h's class; same as the ELF |
| 0x231d80 | `zdb::CVisData::~CVisData()` | already in zvis.h's class (empty); same |
| 0x3030a0-0x3030d0 | `CTextureRelocMgr::AddToBatch / EndBatchReloc / StartBatchReloc / ClearAll` | already in ztex.h's class (empty virtuals); same |
| 0x2f9b70, 0x2f9ca0 | `CBatchRelocator::EndBatchReloc / StartBatchReloc() const` | **not moved: inside fences** in ztexture_holding.cpp (`EndBatchReloc__Q23zdb15CBatchRelocatorFv`, `StartBatchReloc__Q23zdb15CBatchRelocatorFv`); both bodies match the ELF (EndBatchReloc keeps `m_pktbuf.data()`, the value MakeChain returns) |
| 0x1748a0 | `C2DBitmap::GetAssetLibs(C2D::CLibList &)` | moved ztwod_bitmap.cpp -> ztwod.h's class; same as the ELF (quirk kept: the library is added only when the search result is NULL) |
| 0x2fe8e0 | `C2DLine::~C2DLine()` | moved ztwod_holding.cpp -> ztwod.h's class (`{}`: vtable, then ~C2D) |
| 0x1ff970 | `C2D::Draw(const CMatrix &, zdb::CTextureRelocMgr *)` | already in ztwod.h's class (`{}`); same |
| 0x201270 | `C2DString::Draw(const CMatrix &, zdb::CTextureRelocMgr *)` | already in ztwod.h's class (`{}`); same |
| 0x19b0f0 | `CAiMap::GetLocation(const CPnt3D *, CAiMapLoc &) const` | already in zai.h's class; same (the NaN cases agree too) |
| 0x1ca770 | `zdb::CWorld::GetTexHandle(const char *)` | **not moved: inside a fence** in znode_holding.cpp (`GetTexHandle__Q23zdb6CWorldFPc`); matches |
| 0x1bc4a0 | `zdb::CNode::GetBBox() const` | **not moved: inside a fence** in znode_holding.cpp (`GetBBox__Q23zdb5CNodeFv`); matches (m_use_parent_bbox bit 30 of +0x5c, parent +0x64, recursion) |
| 0x1ff660 | `CValve::Set(unsigned int)` | **not moved: inside a fence** in zvalve_holding.cpp (`Set__6CValveFi`); matches |
| 0x3a75a0 | `_zrdr::Get(unsigned int)` | already inline in zrdr.h's class; same (the zreader_holding.cpp copy is a fenced `#if 0`) |

The five fenced bodies wait for the coordinator: moving them means emptying a held fence.
`src/gamez/zNode/znode_holding.cpp` showed as modified at the start but only its working-copy line
endings differed (CRLF against LF in the index); it was not edited.

`CButtonSpec` / `CTextSpec` copy constructors (unchanged by decision): the port writes neither
(zui_spec.cpp has only the `_zrdr` constructors); `Copy()` in zui_cleanup.cpp uses GCC's implicit
`CTextSpec(CTextSpec &)` / `CButtonSpec(CButtonSpec &)` (non-const because the written base
`CDlgObjSpec(CDlgObjSpec &)` is). The ELF's 0x3a0520 / 0x39f570 are the inline base copy (a deep
copy of `m_uivar`) followed by plain memberwise copies (strings, floats, bytes, the four button
states, `vector<ActionItem>` built from the other's range): the implicit constructors do exactly
that.

## Task 2: the old AI map formats

`CAiMap::Read` 0x189390 switches on the version word (jump table 0x449380, 0-19; 0, 1 and 20 on
return false). Everything is now written (`src/gamez/zAI/ai_mapio.cpp`); the old on-disk records
are declared in `zai.h` after `CAiMap`. DWARF has none of them: `action_v15`, `action_v18`,
`region_v4` (and their vectors) are named by the converters' template arguments and laid out from
the converters; `cell_v2` / `cell_v3` are port names (read_cells reads them into locals).

| version | what it reads (on top of / instead of the previous) |
| --- | --- |
| 0, 1 | nothing: false |
| 2 | 52-byte parameter head (`m_bbox` .. `m_floor`, read into a local and copied), cells as 12-byte `cell_v2` |
| 3 | as 2, cells as 8-byte `cell_v3` |
| 4 | + names, actions as 24-byte `action_v15`, links, regions as 24-byte `region_v4`, spores |
| 5 | + `m_name` (32) after the head |
| 6 | + lines (no `line_data` word before 10) |
| 7, 8 | + `m_resolution`; cells current from 8 |
| 9 | regions in the current layout |
| 10 | + `m_flags`; lines carry `line_data` |
| 11, 12 | + `m_slope_threshold` |
| 13 | the whole 164-byte parameters; + the map extra bytes (`m_mapex_bytes` per cell) at the end |
| 14 | + readers |
| 15 | + scanlines after the cells (compressed cells) |
| 16, 17 | actions as 36-byte `action_v18` |
| 18 | + routes |
| 19 | actions in the current 40-byte layout (the disc) |

After the switch: < 12 every link dropped (SetCellLink), < 15 one full-width scanline per row and
`m_cellcount = nx * ny`, < 17 every action's `m_offset` 8; then (when the layout was known)
ValidateCells, ValidateRoutes and CreateGraph.

Conversions:
- cells (read_cells 0x188f60, jump table 0x449330): v2 (0x18900c) soil (4 bits), name, action, link,
  A* dir / f / g; v3-7 (0x189168) also altitude (bits 8-17), boundary (18-19), mes (20). Soil is
  widened to 5 bits, `m_occupied` 0, everything the old record lacks 0 (the cells are memset first).
  Versions 0, 1, 8-16 and 17 on: the current 8-byte cell read whole.
- `action_v15` (0x18a940): type moves from bit 20 to 23 (the new 3-bit `m_state` stays 0),
  `m_offset` 8, `m_locEx[0..2]` kept and `[3..5]` invalid; +0x8 of the old record is not read.
- `action_v18` (0x18ad00): `m_offset`, `m_type_invalid` and all six extra locations copied,
  `m_region` invalid. ELF quirk kept: the action id is not copied (the action keeps the element
  default `action::invalid`, 0xffff).
- `region_v4` (0x18ab70): location, dx, dy, 15 name characters (+ NUL), `m_type` 0; `m_nodisplay` 1
  from the element default.
- Element defaults: the ELF's `resize` copies an inline-constructed element (action 0x18b300: id
  `action::invalid`, `m_offset` 8; region 0x18c560: `m_nodisplay` 1). The port's records keep their
  implicit constructors, so `DefaultRecord` applies those values to the new elements. Port
  deviation: what the ELF leaves unset there (the locations of a stack temporary, e.g. a v4-15
  action's `m_region`) is 0 in the port.

ELF quirk noted, not changed: the < 12 link drop runs before the < 15 scanlines exist, so
SetCellLink's GetCell indexes an empty scanline vector; a map older than 12 with links would read
and write through a NULL row. The test files carry no links before version 12.

### Tests

- (a) The disc's maps load as before: the `aimapio` hook's per-map line (counts and FNV-1a sums of
  the cells, the tables, the scanlines and the extra bytes) from a HEAD-only tree and from this
  tree, m8 with HEAD's `pad_start.txt`: identical for all four maps (BaseMap 265 x 414, 72991
  cells, cellsum 1b0986af, tablesum 7131a0cd, exsum 915b133c; Dredge1, Dredge2, Lodge likewise).
- (b) `port/test-hooks/aimapio/` with `-DAIMAPIO_SELFTEST`: synthetic files written from the
  declared layouts (every bit a converter must not take set to 1), served through `CBufferIO`:
  `read_cells` on a 2 x 2 map for versions 0-18 and the whole `Read` for 0-20 (result, parameters,
  converted cells / actions / regions, links, spores, lines, scanlines, extra bytes, and that the
  reader stopped exactly at the end of the file). Record sizes 12 / 8 / 24 / 36 / 24 as the ELF;
  40 tests, 0 failed.

## Smoke runs

- Default build (no hook, no fake pad): `MENU: CMenuState::Init done` at 15.6 s, the attract
  screens after it.
- Fake-pad m8, 150 s (the self-test build): the map loads at 48 s, the mission plays on with the
  team and HUD (a sentry objective completed by 145 s), no exceptions.

## Files

`src/gamez/zMath/zmath.h`, `zmath_matrix.h`, `src/gamez/zNode/node_model.cpp`,
`src/Apps/FTS/hud/hud_lensflare.cpp`, `src/gamez/zTwoD/ztwod.h`, `ztwod_bitmap.cpp`,
`ztwod_holding.cpp`, `src/gamez/zAI/zai.h`, `ai_mapio.cpp`, `port/test-hooks/aimapio/`
(`hook_aimapio.cpp`, `build.sh`); the `port/test-hooks/README.md` row is an edit file.
