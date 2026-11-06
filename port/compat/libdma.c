/* Functional port lane: the Sony libdma calls the game uses, reimplemented on the EE
 * DMAC registers from the copies linked into socom.elf (addresses below). Not Sony
 * code; nothing here is evidence for the matching lane. */
#include <libdma.h>

#define D_CTRL (*(volatile unsigned int *)0x1000e000)
#define D_STAT (*(volatile unsigned int *)0x1000e010)
#define D_PCR (*(volatile unsigned int *)0x1000e020)
#define D_SQWC (*(volatile unsigned int *)0x1000e030)
#define D_RBSR (*(volatile unsigned int *)0x1000e040)
#define D_RBOR (*(volatile unsigned int *)0x1000e050)

void socom_port_trace(const char *fmt, ...);

static sceDmaChan *const dch[10] = {
    (sceDmaChan *)0x10008000, (sceDmaChan *)0x10009000, (sceDmaChan *)0x1000a000,
    (sceDmaChan *)0x1000b000, (sceDmaChan *)0x1000b400, (sceDmaChan *)0x1000c000,
    (sceDmaChan *)0x1000c400, (sceDmaChan *)0x1000c800, (sceDmaChan *)0x1000d000,
    (sceDmaChan *)0x1000d400,
};

/* Channels sceDmaReset clears (isclr, 0x4455f8); the SIF channels 5-7 belong to the IOP link. */
static const int isclr[10] = {1, 1, 1, 1, 1, 0, 0, 0, 1, 1};

/* CheckAddress: scratchpad addresses get the SPR bit, others lose the segment bits. */
static void *check_address(void *addr)
{
    unsigned int a = (unsigned int)addr;
    if ((a >> 28) == 7)
        return (void *)((a & 0x3fff) | 0x80000000);
    return (void *)(a & 0x0fffffff);
}

static void wait_dma(sceDmaChan *d)
{
    unsigned int n = 0;
    while (((volatile unsigned int *)d)[0] & 0x100) {
        if (++n == 0x1000000) {
            socom_port_trace("libdma: channel %p still busy (chcr %08x)", (void *)d, ((volatile unsigned int *)d)[0]);
            n = 0;
        }
    }
}

/* 0x14fd60 */
int sceDmaReset(int mode)
{
    unsigned int ctrl = D_CTRL;
    int i;

    for (i = 9; i >= 0; i--) {
        if (isclr[i]) {
            volatile unsigned int *r = (volatile unsigned int *)dch[i];
            r[0x20] = 0; /* sadr */
            r[0] = 0;    /* chcr */
            r[0xc] = 0;  /* tadr */
            r[4] = 0;    /* madr */
            r[0x14] = 0; /* as1 */
            r[0x10] = 0; /* as0 */
        }
    }
    D_STAT = 0xff1f;
    D_STAT = D_STAT & 0xff1f0000;
    /* sceDmaPutEnv (0x14fe40) of an all-zero environment: STS/STD/MFD/RELE cleared,
     * PCR, SQWC, RBOR and RBSR zeroed. port: unproven - the STS/STD/MFD lookup tables at
     * 0x445620.. are assumed to map 0 to 0 */
    D_CTRL = D_CTRL & ~0xfeu;
    D_PCR = 0;
    D_SQWC = 0;
    D_RBOR = 0;
    D_RBSR = 0;
    if (mode == 1)
        D_CTRL = D_CTRL | 1;
    return ctrl & 1;
}

/* 0x14fd38 */
sceDmaChan *sceDmaGetChan(int id)
{
    if ((unsigned int)id < 10)
        return dch[id];
    return 0;
}

/* 0x150068: chain mode from tag */
void sceDmaSend(sceDmaChan *d, void *tag)
{
    void *a = check_address(tag);
    volatile unsigned int *r = (volatile unsigned int *)d;
    wait_dma(d);
    if (r[0xc] != 0xffffffff)
        r[0xc] = (unsigned int)a;
    r[8] = 0;
    r[0] = (r[0] & 0xfffffff3) | 0x105;
}

/* 0x1500d0: normal mode, size in quadwords */
void sceDmaSendN(sceDmaChan *d, void *addr, int size)
{
    void *a = check_address(addr);
    volatile unsigned int *r = (volatile unsigned int *)d;
    wait_dma(d);
    if (r[4] != 0xffffffff)
        r[4] = (unsigned int)a;
    r[8] = size;
    r[0] = (r[0] & 0xfffffff3) | 0x101;
}

/* 0x150308: mode 1 polls, otherwise waits */
int sceDmaSync(sceDmaChan *d, int mode, int timeout)
{
    (void)timeout;
    if (mode == 1)
        return (((volatile unsigned int *)d)[0] >> 8) & 1;
    wait_dma(d);
    return 0;
}
