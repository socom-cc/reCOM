# boot-vu1 notes (2026-11-06)

Scratch for the VU microcode work of the functional port. Nothing here is tracked; never copy
`ref_*.bin` (ELF bytes) into src/ or port/.

## Result
- `src/gamez/zRender/zrndr_vu1.vsm` (vu1_CodeSegment1 0x4272e0 + vu1_DataSegment1 0x42aea0) and
  `src/gamez/zRender/zrndr_vu0.vsm` (vu0_CodeSegment 0x426480) assemble with dvp-as to bytes
  IDENTICAL to support/socom.elf 0x4272e0-0x42af5f (15488 B) and 0x426480-0x4272df (3680 B).
  dvp-as also recreates every local symbol of those ranges (.dma.N/.vif.N/.vu.N/_$label: 354 and
  51, all equal), so the label set, label order, the single `MPG 0, *` and code-then-data order of
  the original source are confirmed.
- Port build: `port/CMakeLists.txt` assembles `src/**/*.vsm` with dvp-as into the socom_game
  archive. The linked ELF has section `.vutext` (orphan after .text, in the text PT_LOAD), the three
  globals 16-aligned and byte-identical (`linkcheck.py`). The `.DVP.*` overlay sections are not
  loaded; their names carry a per-run number, so they are not reproducible (unloaded, harmless).
- zRndrInit 0x241850 written (src/gamez/zRender/zrndr_init.cpp); boot: StartEngine completes,
  menus run (frame 300 at 34 s, main menu screenshot `vu1boot-38.png`), no STOP/exception. A
  temporary readback (removed) showed VU1 micro memory = all 3806 code words, VU1 data
  0x147/0x152/0x1a7 = the data segment, VIF1 BASE 0x1a8, OFST 0x12c, TOPS 0x1a8.

## Tools
- `env.sh` (toolchain paths), `extract.py` (reference ranges -> `ref_*.bin`), `gen.py <vu0|vu1>`
  (dvp-objdump text -> `gen_*.vsm` with labels; `labels_*.txt` = label, EE/VU address, chunk),
  `mkfinal.py` (writes the two src/ files from gen_*.vsm + header, .equ names, comments),
  `compare.py <obj> <seg>` (byte compare, lists every differing word), `symcmp.py <obj> <seg>`
  (local symbol compare), `verify.sh` (assemble both src/ files + compare + symcmp),
  `linkcheck.py <port.elf>`, `asm.sh`, `t.sh` (scratch runner),
  `boot.ps1` (copy of boot-mission's, scratch dir = this folder).
- Run from Git Bash: `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu -- bash <script>` (without the env var
  Git Bash rewrites /mnt/c paths).
- dvp-as: `;` comments (also `/* */`; `#` only at line start); `.equ` names work in offsets,
  immediates and UNPACK addresses; a label used as an immediate gives its VU instruction index
  (`iaddiu vi04,vi00,MY_ENTRY` = 0x384).
- Correction to boot-mission/NOTES.md: VuExecuteState0 appends VIF 0x15000000 = **MSCALF 0**
  (not MSCNT); MSCNT is 0x17000000 (used by CDecal::AddDecal 0x312e80).

## VU1 program (details in the .vsm header)
- Entry by VIF: object packet = UNPACK (FLG, TOPS-relative) header + MSCALF 0 -> `VU1_STATE_0`
  (state 0). Batch packets = UNPACK + MSCNT -> resume after `vuSleep` ([E] at VU 888) at
  `vuProcessCommands` (890): vi01 = XTOP, vi14 = 0, then `vuProcessNextCommand` jumps to
  `MY_ENTRY` (900) + command code (x of VU1_PROGRAM[vi14]); every handler ends with
  `b vuProcessNextCommand`; command 66 = `vuSleep`. So state 0 installs a per-object command list
  (VU 340..), and that list runs once per batch.
- State 0 header (from XTOP): hdr[0] = {x light qwords, y command entries, z multipass entries,
  w flags: bit0 matrix setup, bit1 "GS packet only" -> copies hdr[1..8] to VU 330 and XGKICKs};
  hdr[1].x local-light qwords; hdr[2] obj params (clip word, light scales); hdr[3] unused;
  hdr[4..5] fog; hdr[6..9] ModelToWorld; hdr[10..16] camera vectors (CCamera +976) in model space;
  hdr[17] add colour (w opacity); hdr[18] scale colour; hdr[19..26] optional lights; then command
  entries {x code, y resume index, z count, w -}, local lights, multipass entries.
  VuUpdate builds it: SPR packet qword 0 = DMA CNT + STCYCL + UNPACK (VuExecuteState0),
  qword 1 = hdr[0] (tag_ObjectHeader*, y = entry count, w |= 1), VuObjectSetup writes hdr[2..18].
- VU1 data memory (qwords): 0-3 MVP, 4-7 world->clip, 8-11 second world matrix, 16-19 light
  dirs, 20-23 light colours, 26 shadow GIF tag, 27 obj params, 28-29 fog, 30-36 camera vectors,
  39 multipass state, 40.. vertex work buffer A (STQ, RGBA, XYZ per vertex), 112 clipped-polygon
  GS packet, 150.. work buffer B, 290/300 two per-triangle GS packets, 327 add colour, 328 scale
  colour, 329 kick-buffer pointers, 330-337 texture GS packet, 338 (128,128,128,128), 340-359
  command list, 360-399 multipass, 400-422 local lights, 423 GIF EOP tag, 424-723 / 724-1023
  input double buffer (BASE 0x1a8, OFFSET 0x12c).
- Batch layout: [1] GIF tag (strips: NLOOP = vertex count), [2] {x triangle-list offset from
  XTOP, z vertex count, w triangle count}, [3] decompression offset xyz / scale w, [4..] packed
  vertices, 3 qwords each (position itof4 + [3].xyz or itof15 * [3].w, ST itof12 + normal itof15,
  colour itof0). Triangle list entries are 2 qwords: {x, y, z vertex offsets (3 * index into
  VU 40..), w flags (bit 0 visible/kick)}, then a face plane (vuFrontFace reads it).
- vuGatherFixKick builds one 10-qword GS packet per triangle: tag = batch[1] with NLOOP 3 + EOP,
  then STQ, RGBA (+ add colour), XYZ (ftoi4) for each vertex; so the batch GIF tag must declare
  NREG 3 (ST/Q, RGBA, XYZ2/XYZF2) and the PRIM.

## VU0
- Uploaded by zMath_Init 0x2205b0 (CGame::StartEngine; port stub at src/gamez/zMath/zmath_main.cpp)
  through CVU::Code 0x2f5d30 (port stub, src/gamez/zSystem/zsys_spr.cpp). Not part of zRndrInit.
- VCALLMS slots: 2/4 CDIPoly::GetIntersect 0x21d980, 8 CDIBBox::GetIntersect 0x21d580 and
  CBBox::GetIntersect 0x221880, 12 CQuat::Apply 0x221240 (port body is a C guess). Slots 0, 6,
  10 have no EE caller.

## Changed outside my files (minimal, for zRndrInit's direct callees)
- `src/gamez/zVisual/vis_main.cpp`: CVisual::Init 0x30e250 body. `src/gamez/zVisual/zvis.h`:
  CVisual::Init made static (zRndrInit calls it without an object).
- `port/compat/libgraph.c` + `include/libgraph.h`: sceGsSetDefAlphaEnv 0x14f048, sceGsAlphaEnv.

## Still missing before world triangles draw
1. Mission load to a player and CCoreState (other worker).
2. CMesh::Init 0x30fa90 (vis_mesh.cpp stub; `locals` = 1184-byte malloc, `localsI` = 0; `locals`
   is typed `static int` in the port).
3. EE packet builders, all stubs or provisional: CVisual::VuUpdate 0x30a900, VuObjectSetup
   0x30c350, VuBatchProgram 0x30bda0, VuExecuteState0 0x30b740, SaveTextureSelect 0x30bcd0,
   GetChainData 0x30c7c0, GetTextureSelectBlock_ver2 0x30d9b0, Vu{Detail,Shadow,Light}Map,
   VuBatchProgram_Decals 0x30c9c0; CSPR::Copy 0x2f57b0 / Kick 0x2f5810, zSysSprGetPacket
   0x2f5ab0, zSysFifoKick 0x2f5900; tag_ObjectHeader is an empty struct in zvis.h.
4. The camera VU matrix set: CCamera ctor 0x1e7780 stores the packet pointer at +0x3c0,
   CCamera::Update 0x1e7f30 fills +976.. ; CPipe::RenderWorld kicks 25 qwords of it each frame
   (VU 4-26: world->clip etc., port: unproven coverage).
5. Pipe: RenderAtom 0x245810, FIFO_Insert/Signal, CAlpha::Render stubs; RenderNode/Visual/Mesh
   provisional.
6. A quick standalone test is possible now: one object packet (hdr[0] = {0, 4, 0, 1}, identity
   ModelToWorld, an UNPACK of a world->clip matrix to VU 4) with commands 104 (decompress),
   8 (xform), 40 (gather/kick), 66 (sleep), then one batch with 3 vertices and one triangle entry.
   Untested; the batch formats above come from the microcode only.
