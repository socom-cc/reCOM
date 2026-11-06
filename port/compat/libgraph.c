/* Functional port lane: the Sony libgraph calls the game uses, reimplemented from the
 * copies linked into socom.elf (addresses below) on the GS/VIF/GIF registers and the
 * ps2sdk kernel (SetGsCrt, GsPutIMR). Not Sony code; nothing here is evidence for the
 * matching lane. */
#include <libgraph.h>
#include <kernel.h>

void socom_port_trace(const char *fmt, ...);

#define GS_CSR (*(volatile unsigned long long *)0x12001000)
#define VIF1_STAT (*(volatile unsigned int *)0x10003c00)
#define VIF1_FBRST (*(volatile unsigned int *)0x10003c10)
#define VIF1_ERR (*(volatile unsigned int *)0x10003c20)
#define VIF1_FIFO ((volatile unsigned int *)0x10005000)
#define GIF_CTRL (*(volatile unsigned int *)0x10003000)
#define GIF_STAT (*(volatile unsigned int *)0x10003020)
#define D1_CHCR (*(volatile unsigned int *)0x10009000)
#define D2_CHCR (*(volatile unsigned int *)0x1000a000)

/* 0x42b2a0 initial values: interlace, NTSC, frame, version 3 */
static sceGsGParam gparam = {1, 2, 1, 3, 0, 0};

/* VIF1 register defaults written by sceGsResetPath (_init_vif_regs, 0x42b2b0):
 * STCYCL 0x404, STMASK 0, STMOD 0, MSKPATH3 0, BASE 0, OFFSET 0, ITOP 0. */
static const unsigned int init_vif_regs[8] __attribute__((aligned(16))) = {
    0x01000404, 0x20000000, 0x00000000, 0x05000000,
    0x06000000, 0x03000000, 0x02000000, 0x04000000,
};

static unsigned int vu_stat(void)
{
    unsigned int v;
    __asm__ volatile("cfc2 %0, $vi29" : "=r"(v));
    return v;
}

/* 0x14e0e8 */
sceGsGParam *sceGsGetGParam(void)
{
    return &gparam;
}

/* 0x14df58 */
void sceGsResetGraph(short mode, short inter, short omode, short ffmode)
{
    sceGsGParam *gp;

    if (mode == 1) {
        GS_CSR = 0x100;
        return;
    }
    if (mode == 0) {
        gp = sceGsGetGParam();
        GS_CSR = 0x200;
        gp->sceGsInterMode = inter;
        gp->sceGsOutMode = omode;
        gp->sceGsVersion = (short)((GS_CSR >> 16) & 0xff);
        GsPutIMR(0xff00);
        gp->sceGsFFMode = ffmode != 0;
        if (gp->sceGsVSCfunc != 0) {
            DisableIntc(2);
            RemoveIntcHandler(2, gp->sceGsVSCid);
            gp->sceGsVSCid = 0;
            gp->sceGsVSCfunc = 0;
        }
        SetGsCrt(inter & 1, omode & 0xff, ffmode & 1);
        return;
    }
    if (mode == 5) {
        gp = sceGsGetGParam();
        gp->sceGsFFMode = ffmode != 0;
        gp->sceGsInterMode = inter;
        gp->sceGsOutMode = omode;
        gp->sceGsVersion = (short)((GS_CSR >> 16) & 0xff);
        SetGsCrt(inter & 1, omode & 0xff, ffmode & 1);
    }
}

/* 0x14e0f8: reset VIF1, VU1 and GIF, then reload the VIF1 defaults through its FIFO. */
void sceGsResetPath(void)
{
    unsigned int fbrst;

    VIF1_FBRST = 1;
    VIF1_ERR = 2;
    __asm__ volatile("sync.l");
    __asm__ volatile("cfc2 %0, $vi28" : "=r"(fbrst));
    fbrst |= 0x200;
    __asm__ volatile("ctc2 %0, $vi28" : : "r"(fbrst));
    __asm__ volatile("sync.p");
    __asm__ volatile(
        "lq $8, 0(%0)\n\t"
        "sq $8, 0(%1)\n\t"
        "lq $8, 16(%0)\n\t"
        "sq $8, 0(%1)\n\t"
        : : "r"(init_vif_regs), "r"(VIF1_FIFO) : "$8", "memory");
    GIF_CTRL = 1;
}

/* 0x14ec98: wait for the next vertical blank; in interlace mode return the field. */
int sceGsSyncV(int mode)
{
    sceGsGParam *gp = sceGsGetGParam();
    (void)mode;
    GS_CSR = 8; /* clear VSINT */
    while ((GS_CSR & 8) == 0)
        ;
    if (gp->sceGsInterMode == 1)
        return (int)((GS_CSR >> 13) & 1);
    return 1;
}

/* 0x14ed30: mode 0 waits for VIF1/GIF DMA, VIF1, VU1 and GIF to go idle. */
int sceGsSyncPath(int mode, unsigned short timeout)
{
    unsigned int n = 0;
    unsigned int r;
    (void)timeout;

    if (mode == 0) {
        while (D1_CHCR & 0x100)
            if (++n > 0x1000000)
                goto stuck;
        while (D2_CHCR & 0x100)
            if (++n > 0x1000000)
                goto stuck;
        while (VIF1_STAT & 0x1f000003)
            if (++n > 0x1000000)
                goto stuck;
        while (vu_stat() & 0x100)
            if (++n > 0x1000000)
                goto stuck;
        while (GIF_STAT & 0xc00)
            if (++n > 0x1000000)
                goto stuck;
        return 0;
    stuck:
        socom_port_trace("sceGsSyncPath: path stuck (D1 %08x D2 %08x VIF1 %08x GIF %08x)",
                         D1_CHCR, D2_CHCR, VIF1_STAT, GIF_STAT);
        return -1;
    }

    r = (D1_CHCR & 0x100) != 0;
    if (D2_CHCR & 0x100)
        r |= 2;
    if (VIF1_STAT & 0x1f000003)
        r |= 4;
    if (vu_stat() & 0x100)
        r |= 8;
    if (GIF_STAT & 0xc00)
        r |= 0x10;
    return (int)r;
}

/* 0x14e648: z buffer page after one frame buffer of w x h (two when not frame mode). */
short sceGszbufaddr(short psm, short w, short h)
{
    sceGsGParam *gp = sceGsGetGParam();
    int pw = (w + 0x3f) >> 6;
    int ph = (psm & 2) == 0 ? (h + 0x1f) >> 5 : (h + 0x3f) >> 6;
    int pages = pw * ph;
    if (gp->sceGsInterMode == 1 && gp->sceGsFFMode == 0)
        return (short)pages;
    return (short)(pages * 2);
}

/* 0x14e210 (NTSC, PAL and 480p branches; the OSD dx/dy model offsets are 0 for NTSC/PAL). */
void sceGsSetDefDispEnv(sceGsDispEnv *disp, short psm, short w, short h, short dx, short dy)
{
    sceGsGParam *gp = sceGsGetGParam();
    unsigned short om = (unsigned short)gp->sceGsOutMode;
    short inter = gp->sceGsInterMode;
    long long dxoff = 0, dyoff = 0;
    int magh;
    unsigned long long dh, dyv, dxv;

    disp->pmode = 0x66;
    if (inter == 0)
        disp->smode2 = 2;
    else
        disp->smode2 = gp->sceGsFFMode == 0 ? 1 : 3;
    disp->dispfb = ((unsigned long long)(psm & 0xf) << 15) | ((unsigned long long)(((w + 0x3f) >> 6) & 0x3f) << 9);

    if (om == 2 || om == 3) {
        int x0 = om == 2 ? 0x27c : 0x290;
        magh = (w + 0x9ff) / w;
        dxv = (unsigned long long)((long long)dx * magh + dxoff + x0) & 0xfff;
        if (inter != 1) {
            dyv = (unsigned long long)(dy + dyoff + (om == 2 ? 0x19 : 0x24)) & 0xfff;
            dh = (unsigned long long)(h - 1);
        } else {
            dyv = (unsigned long long)(dy + dyoff + (om == 2 ? 0x32 : 0x48)) & 0xfff;
            dh = gp->sceGsFFMode == 0 ? (unsigned long long)(h - 1) : (unsigned long long)(h * 2 - 1);
        }
        disp->display = ((unsigned long long)(magh - 1) << 23) | ((unsigned long long)(magh * w - 1) << 32) |
                        dxv | (dh << 44) | (dyv << 12);
    } else if (om == 0x50) {
        disp->display = ((unsigned long long)(h - 1) << 44) | ((unsigned long long)(w * 2 - 1) << 32) |
                        ((unsigned long long)(((0x2d0 - w) / 2 << 1) + dxoff + (dx << 1) + 0xe8) & 0xfff) |
                        0x800000 | ((unsigned long long)(dy + dyoff + 0x23) & 0xfff) << 12;
    } else {
        socom_port_trace("sceGsSetDefDispEnv: unsupported output mode %d", om);
    }
    disp->bgcolor = 0;
}

/* 0x14e710 */
int sceGsSetDefDrawEnv(sceGsDrawEnv1 *draw, short psm, short w, short h, short ztest, short zpsm)
{
    unsigned long long zbp;

    draw->frame1addr = 0x4c;
    draw->frame1 = ((unsigned long long)(((w + 0x3f) >> 6) & 0x3f) << 16) | ((unsigned long long)(psm & 0xf) << 24);
    draw->zbuf1addr = 0x4e;
    zbp = (unsigned long long)(long long)sceGszbufaddr(psm, w, h);
    draw->zbuf1 = zbp | ((unsigned long long)(zpsm & 0xf) << 24) | (ztest == 0 ? 0x100000000ull : 0);
    draw->xyoffset1addr = 0x18;
    draw->xyoffset1 = ((unsigned long long)(0x800 - (w >> 1)) << 4) | ((unsigned long long)(0x800 - (h >> 1)) << 36);
    draw->scissor1addr = 0x40;
    draw->scissor1 = ((unsigned long long)(w - 1) << 16) | ((unsigned long long)(h - 1) << 48);
    draw->prmodecontaddr = 0x1a;
    draw->prmodecont |= 1;
    draw->colclampaddr = 0x46;
    draw->colclamp |= 1;
    draw->dtheaddr = 0x45;
    if (psm & 2)
        draw->dthe |= 1;
    else
        draw->dthe &= ~1ull;
    draw->test1addr = 0x47;
    draw->test1 = ztest == 0 ? 0x30000 : (((unsigned long long)(ztest & 3) << 17) | 0x10000);
    return 8;
}

/* 0x14e8f8 */
int sceGsSetDefClear(sceGsClear *cp, short ztest, short x, short y, short w, short h,
                     unsigned long long r, unsigned long long g, unsigned long long b, unsigned long long a,
                     unsigned int z)
{
    cp->testaaddr = 0x47;
    cp->testa = 0x30000;
    cp->primaddr = 0;
    cp->prim = 6;
    cp->rgbaqaddr = 1;
    cp->rgbaq = (r & 0xff) | ((g & 0xff) << 8) | ((b & 0xff) << 16) | ((a & 0xff) << 24) | 0x3f80000000000000ull;
    cp->xyz2aaddr = 5;
    cp->xyz2a = (unsigned long long)(x << 4) | ((unsigned long long)(y << 4) << 16) | ((unsigned long long)z << 32);
    cp->xyz2baddr = 5;
    cp->xyz2b = (unsigned long long)((x + w) << 4) | ((unsigned long long)((y + h) << 4) << 16) | ((unsigned long long)z << 32);
    cp->testbaddr = 0x47;
    cp->testb = ztest == 0 ? 0x30000 : (((unsigned long long)(ztest & 3) << 17) | 0x10000);
    return 6;
}

/* 0x14ea00 */
void sceGsSetDefDBuff(sceGsDBuff *dp, short psm, short w, short h, short ztest, short zpsm, short clear)
{
    sceGsGParam *gp = sceGsGetGParam();
    unsigned long long nloop;
    short zbp;

    sceGsSetDefDispEnv(&dp->disp[0], psm, w, h, 0, 0);
    sceGsSetDefDispEnv(&dp->disp[1], psm, w, h, 0, 0);
    sceGsSetDefDrawEnv(&dp->draw0, psm, w, h, ztest, zpsm);
    sceGsSetDefDrawEnv(&dp->draw1, psm, w, h, ztest, zpsm);
    if (clear) {
        sceGsSetDefClear(&dp->clear0, ztest, 0x800 - (w >> 1), 0x800 - (h >> 1), w, h, 0, 0, 0, 0, 0);
        sceGsSetDefClear(&dp->clear1, ztest, 0x800 - (w >> 1), 0x800 - (h >> 1), w, h, 0, 0, 0, 0, 0);
    }
    dp->giftag0.tag[0] = dp->giftag0.tag[1] = 0;
    dp->giftag1.tag[0] = dp->giftag1.tag[1] = 0;
    nloop = clear ? 14 : 8;
    /* NLOOP, EOP, NREG 1 (A+D) */
    dp->giftag0.tag[0] = nloop | 0x8000 | 0x1000000000000000ull;
    dp->giftag1.tag[0] = nloop | 0x8000 | 0x1000000000000000ull;
    dp->giftag0.tag[1] = 0xe;
    dp->giftag1.tag[1] = 0xe;
    zbp = sceGszbufaddr(psm, w, h);
    if ((gp->sceGsInterMode == 1 && gp->sceGsFFMode == 1) || gp->sceGsInterMode == 0) {
        dp->draw0.frame1 = (dp->draw0.frame1 & ~0x1ffull) | ((unsigned long long)(zbp >> 1) & 0x1ff);
        dp->disp[1].dispfb = (dp->disp[1].dispfb & ~0x1ffull) | ((unsigned long long)(zbp >> 1) & 0x1ff);
    }
}

/* 0x14f0a8: transfer of a w x h image in dpsm to (x, y) in the buffer at dbp. */
int sceGsSetDefLoadImage(sceGsLoadImage *lp, short dbp, short dbw, short dpsm, short x, short y, short w, short h)
{
    unsigned long long qwc = 0;

    switch (dpsm) {
    case 0: case 0x30: qwc = (unsigned long long)((w * h) >> 2); break;
    case 1: case 0x31: qwc = (unsigned long long)((w * h * 3) >> 4); break;
    case 2: case 10: case 0x32: case 0x3a: qwc = (unsigned long long)((w * h) >> 3); break;
    case 0x13: case 0x1b: qwc = (unsigned long long)((w * h) >> 4); break;
    case 0x14: case 0x24: case 0x2c: qwc = (unsigned long long)((w * h) >> 5); break;
    }
    if ((long long)qwc >= 0x8000) {
        socom_port_trace("sceGsSetDefLoadImage: image too large (%llu qwords)", qwc);
        return 0;
    }
    lp->giftag1.tag[0] = lp->giftag1.tag[1] = 0;
    lp->giftag0.tag[0] = lp->giftag0.tag[1] = 0;
    lp->giftag1.tag[0] = (qwc & 0x7fff) | 0x0800000000008000ull; /* NLOOP qwc, EOP, FLG IMAGE */
    lp->giftag0.tag[0] = 0x1000000000000004ull;                  /* NLOOP 4, NREG 1 */
    lp->giftag0.tag[1] = 0xe;                                    /* A+D */
    lp->bitbltbuf = ((unsigned long long)(unsigned short)dbp << 32) | ((unsigned long long)dbw << 48) |
                    ((unsigned long long)dpsm << 56);
    lp->bitbltbufaddr = 0x50;
    lp->trxpos = ((unsigned long long)(unsigned short)x << 32) | ((unsigned long long)y << 48);
    lp->trxposaddr = 0x51;
    lp->trxreg = (unsigned long long)w | ((unsigned long long)(unsigned short)h << 32);
    lp->trxregaddr = 0x52;
    lp->trxdiraddr = 0x53;
    lp->trxdir = 0;
    return 6;
}

static unsigned int dma_address(const void *p)
{
    unsigned int a = (unsigned int)p;
    if ((a & 0x70000000) == 0x70000000)
        return (a & 0x0fffffff) | 0x80000000;
    return a & 0x0fffffff;
}

#define D2_QWC (*(volatile unsigned int *)0x1000a020)
#define D2_MADR (*(volatile unsigned int *)0x1000a010)

/* 0x14f3d0: send the 6-qword header, then the image, by normal GIF DMA. */
int sceGsExecLoadImage(sceGsLoadImage *lp, unsigned __int128 *srcaddr)
{
    unsigned int n = 0;

    while (D2_CHCR & 0x100)
        if (++n > 0x1000000)
            goto stuck;
    D2_QWC = 6;
    D2_MADR = dma_address(lp);
    D2_CHCR = 0x101;
    while (D2_CHCR & 0x100)
        if (++n > 0x1000000)
            goto stuck;
    D2_QWC = (unsigned int)lp->giftag1.tag[0] & 0x7fff;
    D2_MADR = dma_address(srcaddr);
    D2_CHCR = 0x101;
    return 0;
stuck:
    socom_port_trace("sceGsExecLoadImage: GIF DMA busy");
    return -1;
}

/* 0x14f048: ALPHA_1 (Cs - Cd) * As + Cd, PABE = pabe, TEXA TA0 0x7f / AEM / TA1 0x81, FBA_1 0;
 * returns the number of A+D registers (4). */
int sceGsSetDefAlphaEnv(sceGsAlphaEnv *ap, short pabe)
{
    ap->alpha1addr = 0x42;
    ap->alpha1 = 0x44;
    ap->pabeaddr = 0x49;
    ap->pabe = (unsigned long long)(long long)pabe;
    ap->texaaddr = 0x3b;
    ap->texa = (0x81ull << 32) | 0x807f;
    ap->fba1addr = 0x4a;
    ap->fba1 = 0;
    return 4;
}
