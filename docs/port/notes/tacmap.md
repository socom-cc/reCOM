# boot-tacmap notes (socom-port-tacmap, 2026-11-13): the tactical map's lines (m8)

## State / next step
- DONE. HEAD 66d011d + mine.txt + edits/ (shared.txt). Runs: tm1 (pad_t1), tm2 (pad_t2, with the
  nav-point edits), tmdflt (default build, main menu at 40 s). Screens in
  build/port/screenshots/36-tactical-map/.
- Next (not done): CZLineMap's ELF quirk check of the bright first horizontal grid line (see
  quirks); C2DTriFan (player-blip / cone clipping on the compass radar), Draw2DLine/Draw3DLine/
  clip3DLine (debug + reticle lines, other callers), claymore / MP-bomb items.

## Written (ELF addresses)
- C2DLine (c2dline.cpp): ctor 0x300980, SetColor 0x300960, SetTrans 0x300930, Load 0x300800,
  SetPos 0x300780, SetUV 0x300760, Draw 0x300700, MakePacket 0x300520 (GS LINE, NLOOP 2, TME by
  m_hasTexture, no +0.5 rounding: vftoi4), FillClipInfo 0x300480, SetClipInfo 0x3003e0,
  GetAssetLibs 0x2ffb20. ztwod.h edit: DWARF members m_x .. do3D (160 bytes).
- C2DWidePolyline::SetSegments 0x2fd370 (c2dbitmap_poly.cpp): quads per segment, mitred joints,
  square last end; _vecSegments member (ztwod.h edit).
- zdb::CCircleClip::CircleSegmentClip 0x220170 (zmath_main.cpp; returns int 0..4, zmath.h).
- WordIntersectionTest 0x3dece0 (hud_teammatenames.cpp).
- CAiMap::GetCellCenter 0x197cb0 (zai.h inline, over GetCellPos).
- CZLineMap (hud_linemap.cpp): dtor 0x3c7210, LineTo 0x3ca5e0, SetupPolygon 0x3c9950 (fan of
  C2DPolys, reused), TickLine 0x3c8cc0 (thin C2DLines or one C2DWidePolyline when width > 1.01;
  current objective's LINE_IDS pulse; other visible maps x0.25), TickLines 0x3c8be0, TickRegions
  0x3c86b0 (region types 1 and 5, _linedata[1]), TickWayPoints 0x3c7a70 ("ABLE" on the player,
  "BRAVO" on the first team-8 seal, AI-map names of type 1/5 (initial only on the small map),
  overlap push-down), Clip 0x3c76e0, CAiLinePtItr (Advance 0x3cab20, GetPt 0x3cabe0, IsValid
  0x3c91c0, FindValid 0x3c90f0); Tick/Draw adapted to the typed vectors. hud.h edit: vectors
  C2DPoly* / C2DWidePolyline*, dtor out of line, CZNewHudMap::WorldToDraw 0x3c8b10 (inline).
- Nav points (edit files, missionwin's files): FilterNavPointString 0x1f8700 ('c'..'z' -> anchor
  types 9..32), CMission::CreateCompassNavPoints 0x1f85f0 (AiMaps.m_names[1]), m_navpoints
  (zfts.h, DWARF +0x8c), Close deletes them (0x1f7584 loop, swap) - m8: 9 nav points.
- Shared code: the full-screen map and the compass map use the same CZLineMap item (one item in
  CZNewHudMap::m_itemlist); the small map is only drawn with gopt.doRadar (off), where Clip's
  circle clip applies; on the full-screen map the clip circle is 4 half-widths (nothing cut) and
  the GS scissor (CZNewHudMap::Draw) clips to the frame.

## Results
- tm2.log: map 0: 43 lines / 22 labels / 186 polygon triangles / 0 wide lines at default zoom
  (AI map: 128 lines, 30 regions, 169 names); zoom in -> 26 lines, zoom out -> 99. Player blip
  with "ABLE" at 2251 4729, secondary star on Charlie, Cabin / Weapons Shed / Delta / Echo /
  Romeo labels on their buildings. CORE frames 59.9/s with the map open and closed (no slowdown).
  Mission to 205 s, no STOP, heap 21.95 MB (map open 65 s) -> 22.10 MB (205 s).
- tmdflt: default build at the main menu (tmdflt.png).

## ELF quirks kept
- C2DLine::Load with no texture clears `first` and places nothing; Draw needs a texture.
- TickWayPoints' labels skip CalcDrawPos (only the matrix). CircleSegmentClip writes its scratch
  into m_rCx/m_rCy and po0.x/po1.x even when it returns 0. SetClipInfo ignores its count.
- Now that C2DLine draws, the full-screen grid shows its ELF quirk: the first horizontal grid
  line (CZNewHudMap ctor, trans 128) is a bright white line across the map; the north arrow
  shafts are visible too.

## Port deviations
- TickLine has its own copy of c_arrTypes (the ELF reads SetupPolygon's 0x465618: inline lookup).
- TickWayPoints skips a label when the 32 are used up (the ELF writes through NULL).
- CircleSegmentClip writes sceVu0InterVector out as a lerp.
- FindLineData / IsObjectiveLine / NextMapString / LoadMapString: file-local helpers for code the
  ELF inlines (no symbols).
- Port trace "TACMAP:" every 2 s while the full-screen map is open (hud_linemap.cpp Tick).

## Tools
- `HOOKSH=hookt.sh bash tb.sh <build> <pad> x` (PowerShell: `$env:WSLENV='HOOKSH/u'`):
  hook_tacmap.cpp keeps the player's health full, traces his position. Build names `tm*`.
- `build_default.sh <build>`: fresh HEAD + mine + shared edits, no hooks.
- go.ps1 <build> <name> <seconds> "<shots>". In pad_t2: read 1000 SELECT opens the map
  (~78 s), DOWN x2 selects BRAVO TO CHARLIE, CIRCLE centres it, RY=0 zooms in, LX scrolls, RY=255
  zooms out, SQUARE, SELECT closes (~96 s).
