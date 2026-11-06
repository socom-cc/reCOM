## zrender/zrndr_vu1.vsm
Note: user decision 2026-11-06 ("Put it in src/gamez/zRender as zrndr_vu1.vsm"). VU1 microcode and its data segment, written as VU assembly. The ELF keeps only symbols for it: global `vu1_CodeSegment1` (0x4272e0) and `vu1_DataSegment1` (0x42aea0), and local `_$VU1_*` labels (e.g. `_$VU1_STATE_0`, `_$VU1_TRI_CLIPPER`, `_$VU1_LINE_CLIPPER`). zRndrInit 0x241850 uploads both.
- vu1_CodeSegment1
- vu1_DataSegment1
