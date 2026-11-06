## zrender/zrndr_vu1.vsm
Note: user decision 2026-11-06 ("Put it in src/gamez/zRender as zrndr_vu1.vsm"). VU1 microcode and its data segment, written as VU assembly. The ELF keeps only symbols for it: global `vu1_CodeSegment1` (0x4272e0) and `vu1_DataSegment1` (0x42aea0), and local `_$VU1_*` labels (e.g. `_$VU1_STATE_0`, `_$VU1_TRI_CLIPPER`, `_$VU1_LINE_CLIPPER`). zRndrInit 0x241850 uploads both.
- vu1_CodeSegment1
- vu1_DataSegment1

## zrender/zrndr_vu0.vsm
Note: user decision 2026-11-06 ("Put the VU0 program in zrndr_vu0.vsm too"). VU0 microcode, written as VU assembly. The ELF keeps only symbols for it: global `vu0_CodeSegment` (0x426480, up to `vu1_CodeSegment1` at 0x4272e0) and local `_$vu0*` labels (e.g. `_$vu0QuatApply`, `_$vu0QuatToMatrix`, `_$vu0IntersectBBox`, `_$vu0GetIntersect`, `_$vu0IntersectWithEdges`). The Sony `sceVu0*` EE functions are not part of it.
- vu0_CodeSegment
