/* Port compatibility header: the Sony EE eeregs.h register pointers the game uses
 * (Sony style: dereference to access, e.g. *GS_PMODE = 0). Each name is guarded
 * because ps2sdk's timer.h defines some of the same names with the same values.
 * Shared and append-only: add declarations, never rewrite or reorder others' lines. */
#ifndef SOCOM_COMPAT_EEREGS_H
#define SOCOM_COMPAT_EEREGS_H

/* timers */
#ifndef T0_COUNT
#define T0_COUNT ((volatile unsigned int *)0x10000000)
#endif
#ifndef T0_MODE
#define T0_MODE ((volatile unsigned int *)0x10000010)
#endif

/* VIF */
#ifndef VIF0_FBRST
#define VIF0_FBRST ((volatile unsigned int *)0x10003810)
#endif
#ifndef VIF1_ERR
#define VIF1_ERR ((volatile unsigned int *)0x10003c20)
#endif

/* DMAC */
#ifndef D1_CHCR
#define D1_CHCR ((volatile unsigned int *)0x10009000)
#endif
#ifndef D1_TADR
#define D1_TADR ((volatile unsigned int *)0x10009030)
#endif
#ifndef D2_CHCR
#define D2_CHCR ((volatile unsigned int *)0x1000a000)
#endif
#ifndef D2_TADR
#define D2_TADR ((volatile unsigned int *)0x1000a030)
#endif
#ifndef D8_CHCR
#define D8_CHCR ((volatile unsigned int *)0x1000d000)
#endif
#ifndef D8_MADR
#define D8_MADR ((volatile unsigned int *)0x1000d010)
#endif
#ifndef D8_QWC
#define D8_QWC ((volatile unsigned int *)0x1000d020)
#endif
#ifndef D8_SADR
#define D8_SADR ((volatile unsigned int *)0x1000d080)
#endif
#ifndef D9_CHCR
#define D9_CHCR ((volatile unsigned int *)0x1000d400)
#endif
#ifndef D_CTRL
#define D_CTRL ((volatile unsigned int *)0x1000e000)
#endif
#ifndef D_RBSR
#define D_RBSR ((volatile unsigned int *)0x1000e040)
#endif
#ifndef D_RBOR
#define D_RBOR ((volatile unsigned int *)0x1000e050)
#endif

/* GS privileged registers (64-bit) */
#ifndef GS_PMODE
#define GS_PMODE ((volatile unsigned long long *)0x12000000)
#endif
#ifndef GS_SMODE2
#define GS_SMODE2 ((volatile unsigned long long *)0x12000020)
#endif
#ifndef GS_DISPFB1
#define GS_DISPFB1 ((volatile unsigned long long *)0x12000070)
#endif
#ifndef GS_DISPLAY1
#define GS_DISPLAY1 ((volatile unsigned long long *)0x12000080)
#endif
#ifndef GS_DISPFB2
#define GS_DISPFB2 ((volatile unsigned long long *)0x12000090)
#endif
#ifndef GS_DISPLAY2
#define GS_DISPLAY2 ((volatile unsigned long long *)0x120000a0)
#endif
#ifndef GS_EXTWRITE
#define GS_EXTWRITE ((volatile unsigned long long *)0x120000d0)
#endif
#ifndef GS_BGCOLOR
#define GS_BGCOLOR ((volatile unsigned long long *)0x120000e0)
#endif

/* toSPR channel (CSPR::Copy), VIF1 FBRST and the GIF channel QWC (InterruptFromVIF1) */
#ifndef D9_MADR
#define D9_MADR ((volatile unsigned int *)0x1000d410)
#endif
#ifndef D9_QWC
#define D9_QWC ((volatile unsigned int *)0x1000d420)
#endif
#ifndef D9_SADR
#define D9_SADR ((volatile unsigned int *)0x1000d480)
#endif
#ifndef VIF1_FBRST
#define VIF1_FBRST ((volatile unsigned int *)0x10003c10)
#endif
#ifndef D2_QWC
#define D2_QWC ((volatile unsigned int *)0x1000a020)
#endif

/* GIF (CCoreState::Init 0x17d620 sets MODE bit 2, IMT) */
#ifndef GIF_MODE
#define GIF_MODE ((volatile unsigned int *)0x10003010)
#endif

/* movie player: toIPU channel (playpss nodataCallback), VIF1 channel (CVideo::ReadGsMemory) */
#ifndef D4_CHCR
#define D4_CHCR ((volatile unsigned int *)0x1000b400)
#endif
#ifndef D4_MADR
#define D4_MADR ((volatile unsigned int *)0x1000b410)
#endif
#ifndef D4_QWC
#define D4_QWC ((volatile unsigned int *)0x1000b420)
#endif
#ifndef D1_MADR
#define D1_MADR ((volatile unsigned int *)0x10009010)
#endif
#ifndef D1_QWC
#define D1_QWC ((volatile unsigned int *)0x10009020)
#endif

#endif /* SOCOM_COMPAT_EEREGS_H */
