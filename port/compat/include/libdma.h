/* Port compatibility header: the Sony EE libdma.h. ps2sdk has no libdma of this
 * shape; the calls are reimplemented in port/compat/libdma.c from the copies linked
 * into socom.elf. Layouts follow the game's DWARF (sceDmaChan, 144 bytes; tD_CHCR).
 * Shared and append-only: add declarations, never rewrite or reorder others' lines. */
#ifndef SOCOM_COMPAT_LIBDMA_H
#define SOCOM_COMPAT_LIBDMA_H

/* DMAC channel ids (sceDmaGetChan) */
#define SCE_DMA_VIF0 0
#define SCE_DMA_VIF1 1
#define SCE_DMA_GIF 2
#define SCE_DMA_fromIPU 3
#define SCE_DMA_toIPU 4
#define SCE_DMA_fromSPR 8
#define SCE_DMA_toSPR 9

typedef struct {
	unsigned int DIR : 1;
	unsigned int p0 : 1;
	unsigned int MOD : 2;
	unsigned int ASP : 2;
	unsigned int TTE : 1;
	unsigned int TIE : 1;
	unsigned int STR : 1;
	unsigned int p1 : 7;
	unsigned int TAG : 16;
} tD_CHCR;

struct _sceDmaTag;

/* One DMAC channel's register block (volatile hardware). */
typedef volatile struct {
	tD_CHCR chcr;
	unsigned int p0[3];
	void *madr;
	unsigned int p1[3];
	unsigned int qwc;
	unsigned int p2[3];
	struct _sceDmaTag *tadr;
	unsigned int p3[3];
	void *as0;
	unsigned int p4[3];
	void *as1;
	unsigned int p5[3];
	unsigned int p6[4];
	unsigned int p7[4];
	void *sadr;
	unsigned int p8[3];
} sceDmaChan;

#ifdef __cplusplus
extern "C" {
#endif

int sceDmaReset(int mode);
sceDmaChan *sceDmaGetChan(int id);
void sceDmaSend(sceDmaChan *d, void *tag);
void sceDmaSendN(sceDmaChan *d, void *addr, int size);
int sceDmaSync(sceDmaChan *d, int mode, int timeout);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_LIBDMA_H */
