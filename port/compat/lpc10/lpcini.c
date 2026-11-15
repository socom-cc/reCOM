/* libpttclient lpcini.c (provider): the common block /contrl/ and the creation and reset of the
 * encoder and decoder state records. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* common /contrl/: 12 bytes of .bss at 0x5754d0 in the ELF (one definition here) */
struct lpc10_contrl contrl_;

/* 0x3f1530, 48 bytes */
int lpcini_(void)
{
    contrl_.order = 10;
    contrl_.lframe = 180;
    contrl_.corrp = TRUE_;
    return 0;
}

/* 0x3f1560, 76 bytes: malloc (9540 bytes), then reset; null when malloc fails */
struct lpc10_encoder_state *create_lpc10_encoder_state(void)
{
    struct lpc10_encoder_state *st;

    st = (struct lpc10_encoder_state *)malloc((unsigned)sizeof(struct lpc10_encoder_state));
    if (st != 0) {
        init_lpc10_encoder_state(st);
    }
    return st;
}

/* 0x3f15b0, 1012 bytes. osbuf, fpc and lasti are not set (as in the ELF). */
void init_lpc10_encoder_state(struct lpc10_encoder_state *st)
{
    int i;

    lpcini_();

    /* hp100 */
    st->z11 = 0.f;
    st->z21 = 0.f;
    st->z12 = 0.f;
    st->z22 = 0.f;

    /* analys */
    for (i = 0; i < 540; i++) {
        st->inbuf[i] = 0.f;
        st->pebuf[i] = 0.f;
    }
    for (i = 0; i < 696; i++) {
        st->lpbuf[i] = 0.f;
    }
    for (i = 0; i < 312; i++) {
        st->ivbuf[i] = 0.f;
    }
    st->bias = 0.f;
    st->osptr = 1;
    for (i = 0; i < 3; i++) {
        st->obound[i] = 0;
    }
    st->vwin[4] = 307;
    st->vwin[5] = 462;
    st->awin[4] = 307;
    st->awin[5] = 462;
    for (i = 0; i < 8; i++) {
        st->voibuf[i] = 0;
    }
    for (i = 0; i < 3; i++) {
        st->rmsbuf[i] = 0.f;
    }
    for (i = 0; i < 30; i++) {
        st->rcbuf[i] = 0.f;
    }
    st->zpre = 0.f;

    /* onset */
    st->n = 0.f;
    st->d__ = 1.f;
    for (i = 0; i < 16; i++) {
        st->l2buf[i] = 0.f;
    }
    st->l2sum1 = 0.f;
    st->l2ptr1 = 1;
    st->l2ptr2 = 9;
    st->hyst = FALSE_;

    /* voicin */
    st->dither = 20.f;
    st->maxmin = 0.f;
    for (i = 0; i < 6; i++) {
        st->voice[i] = 0.f;
    }
    st->lbve = 3000;
    st->fbve = 3000;
    st->fbue = 187;
    st->ofbue = 187;
    st->sfbue = 187;
    st->lbue = 93;
    st->olbue = 93;
    st->slbue = 93;
    st->snr = (real)(st->fbve / st->fbue << 6);

    /* dyptrk */
    for (i = 0; i < 60; i++) {
        st->s[i] = 0.f;
    }
    for (i = 0; i < 120; i++) {
        st->p[i] = 0;
    }
    st->ipoint = 0;
    st->alphax = 0.f;

    /* chanwr */
    st->isync = 0;
}

/* 0x3f19b0, 76 bytes: malloc (3072 bytes), then reset; null when malloc fails */
struct lpc10_decoder_state *create_lpc10_decoder_state(void)
{
    struct lpc10_decoder_state *st;

    st = (struct lpc10_decoder_state *)malloc((unsigned)sizeof(struct lpc10_decoder_state));
    if (st != 0) {
        init_lpc10_decoder_state(st);
    }
    return st;
}

/* 0x3f1a00, 612 bytes. ivoico, ipito, rco and jsamp are not set (pitsyn_'s first frame sets them,
 * as in the ELF). */
void init_lpc10_decoder_state(struct lpc10_decoder_state *st)
{
    int i;

    lpcini_();

    /* decode */
    st->iptold = 60;
    st->first = TRUE_;
    st->ivp2h = 0;
    st->iovoic = 0;
    st->iavgp = 60;
    st->erate = 0;
    for (i = 0; i < 30; i++) {
        st->drc[i] = 0;
    }
    for (i = 0; i < 3; i++) {
        st->dpit[i] = 0;
        st->drms[i] = 0;
    }

    /* synths */
    for (i = 0; i < 360; i++) {
        st->buf[i] = 0.f;
    }
    st->buflen = 180;

    /* pitsyn */
    st->rmso = 1.f;
    st->first_pitsyn = TRUE_;

    /* bsynz */
    st->ipo = 0;
    for (i = 0; i < 166; i++) {
        st->exc[i] = 0.f;
        st->exc2[i] = 0.f;
    }
    st->lpi1 = 0.f;
    st->lpi2 = 0.f;
    st->lpi3 = 0.f;
    st->hpi1 = 0.f;
    st->hpi2 = 0.f;
    st->hpi3 = 0.f;
    st->rmso_bsynz = 0.f;

    /* random */
    st->j = 2;
    st->k = 5;
    st->y[0] = (shortint)-21161;
    st->y[1] = (shortint)-8478;
    st->y[2] = (shortint)30892;
    st->y[3] = (shortint)-10216;
    st->y[4] = (shortint)16950;

    /* deemp */
    st->dei1 = 0.f;
    st->dei2 = 0.f;
    st->deo1 = 0.f;
    st->deo2 = 0.f;
    st->deo3 = 0.f;
}
