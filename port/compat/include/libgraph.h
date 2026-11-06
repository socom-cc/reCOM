/* Port compatibility header: declarations the game source takes from the Sony EE
 * libgraph.h. Shared and append-only: add declarations, never rewrite or reorder
 * others' lines. Layouts come from the game's DWARF; `unsigned long` was 64-bit
 * on Metrowerks PS2, so 64-bit fields are spelled `unsigned long long` here. */
#ifndef SOCOM_COMPAT_LIBGRAPH_H
#define SOCOM_COMPAT_LIBGRAPH_H

/* DWARF sceGsAlpha: class, 8 bytes, bitfields of `unsigned long` (8 bytes on MW). */
typedef struct {
	unsigned long long A:2;
	unsigned long long B:2;
	unsigned long long C:2;
	unsigned long long D:2;
	unsigned long long pad8:24;
	unsigned long long FIX:8;
	unsigned long long pad40:24;
} sceGsAlpha;

/* Display / draw environments as the linked libgraph builds them (sceGsSetDefDBuff
 * 0x14ea00 offsets: disp[2] 0x00/0x28, giftag0 0x50, draw0 0x60, clear0 0xe0,
 * giftag1 0x140, draw1 0x150, clear1 0x1d0; 0x230 bytes). Registers are kept as raw
 * 64-bit values (the game edits them with masks). */
typedef struct {
	unsigned long long pmode;
	unsigned long long smode2;
	unsigned long long dispfb;
	unsigned long long display;
	unsigned long long bgcolor;
} sceGsDispEnv;

typedef struct {
	unsigned long long frame1, frame1addr;
	unsigned long long zbuf1, zbuf1addr;
	unsigned long long xyoffset1, xyoffset1addr;
	unsigned long long scissor1, scissor1addr;
	unsigned long long prmodecont, prmodecontaddr;
	unsigned long long colclamp, colclampaddr;
	unsigned long long dthe, dtheaddr;
	unsigned long long test1, test1addr;
} sceGsDrawEnv1;

typedef struct {
	unsigned long long testa, testaaddr;
	unsigned long long prim, primaddr;
	unsigned long long rgbaq, rgbaqaddr;
	unsigned long long xyz2a, xyz2aaddr;
	unsigned long long xyz2b, xyz2baddr;
	unsigned long long testb, testbaddr;
} sceGsClear;

typedef struct {
	unsigned long long tag[2];
} __attribute__((aligned(16))) sceGifTag;

typedef struct {
	sceGsDispEnv disp[2];
	sceGifTag giftag0;
	sceGsDrawEnv1 draw0;
	sceGsClear clear0;
	sceGifTag giftag1;
	sceGsDrawEnv1 draw1;
	sceGsClear clear1;
} sceGsDBuff;

/* sceGsGetGParam (0x14e0e8 -> 0x42b2a0): {interlace, omode, ffmode, version, ...} */
typedef struct {
	short sceGsInterMode;
	short sceGsOutMode;
	short sceGsFFMode;
	short sceGsVersion;
	volatile int sceGsVSCfunc;
	int sceGsVSCid;
} sceGsGParam;

/* sceGsSetDefLoadImage (0x14f0a8) layout: GIF A+D tag, BITBLTBUF, TRXPOS, TRXREG,
 * TRXDIR, then the IMAGE tag at 0x50 (96 bytes; DWARF sceGsLoadImage). */
typedef struct {
	sceGifTag giftag0;
	unsigned long long bitbltbuf, bitbltbufaddr;
	unsigned long long trxpos, trxposaddr;
	unsigned long long trxreg, trxregaddr;
	unsigned long long trxdir, trxdiraddr;
	sceGifTag giftag1;
} sceGsLoadImage;

/* sceGsSetDefAlphaEnv (0x14f048) layout: ALPHA_1, PABE, TEXA, FBA_1 as register/address pairs
 * (64 bytes, the A+D data behind a GIF tag; zRndrInit 0x241850 builds two in ZDB). */
typedef struct {
	unsigned long long alpha1, alpha1addr;
	unsigned long long pabe, pabeaddr;
	unsigned long long texa, texaaddr;
	unsigned long long fba1, fba1addr;
} sceGsAlphaEnv;

#define SCE_GS_NOINTERLACE 0
#define SCE_GS_INTERLACE 1
#define SCE_GS_FIELD 0
#define SCE_GS_FRAME 1
#define SCE_GS_NTSC 2
#define SCE_GS_PAL 3
#define SCE_GS_DTV480P 0x50

#ifdef __cplusplus
extern "C" {
#endif

sceGsGParam *sceGsGetGParam(void);
void sceGsResetGraph(short mode, short inter, short omode, short ffmode);
void sceGsResetPath(void);
int sceGsSyncV(int mode);
int sceGsSyncPath(int mode, unsigned short timeout);
short sceGszbufaddr(short psm, short w, short h);
void sceGsSetDefDispEnv(sceGsDispEnv *disp, short psm, short w, short h, short dx, short dy);
int sceGsSetDefDrawEnv(sceGsDrawEnv1 *draw, short psm, short w, short h, short ztest, short zpsm);
int sceGsSetDefClear(sceGsClear *cp, short ztest, short x, short y, short w, short h,
	unsigned long long r, unsigned long long g, unsigned long long b, unsigned long long a,
	unsigned int z);
void sceGsSetDefDBuff(sceGsDBuff *dp, short psm, short w, short h, short ztest, short zpsm, short clear);
int sceGsSetDefLoadImage(sceGsLoadImage *lp, short dbp, short dbw, short dpsm, short x, short y, short w, short h);
int sceGsExecLoadImage(sceGsLoadImage *lp, unsigned __int128 *srcaddr);
int sceGsSetDefAlphaEnv(sceGsAlphaEnv *ap, short pabe);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_LIBGRAPH_H */
