/* libpttclient analys.c (provider): the encoder's analysis of one frame: buffer shifts, DC bias,
 * pre-emphasis, onsets, voicing window, low-pass and inverse filter, pitch (AMDF + tracker),
 * voicing, analysis / energy windows, RMS and the covariance-method reflection coefficients.
 * Parameters come out two frames late. State in the encoder record. From the reference ELF; see
 * lpc10.h. */
#include "lpc10.h"

/* 0x47557c..0x4755a4 */
static integer c__10 = 10;
static integer c__181 = 181;
static integer c__720 = 720;
static integer c__3 = 3;
static integer c__90 = 90;
static integer c__156 = 156;
static integer c__307 = 307;
static integer c__462 = 462;
static integer c__312 = 312;
static integer c__60 = 60;
static integer c__1 = 1;

/* 0x3eb3a0, 2768 bytes; tau at 0x43c3f0, buflim at 0x43c4e0 (equal to the ELF's data). precoef
 * is a .sbss float set to .9375 (0x3f700000) on the first call under an init$16 guard in the
 * ELF; a plain initialised static here. */
int analys_(real *speech, integer *voice, integer *pitch, real *rms, real *rc,
            struct lpc10_encoder_state *st)
{
    static integer tau[60] = { 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36,
        37, 38, 39, 40, 42, 44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64, 66, 68, 70, 72, 74, 76, 78,
        80, 84, 88, 92, 96, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 148, 152,
        156 };
    static integer buflim[4] = { 181, 720, 25, 720 };
    static real precoef = .9375f;

    integer i__1;
    real amdf[60];
    integer half;
    real abuf[156];
    real *bias;
    integer *awin;
    integer midx, ewin[6]; /* was [2][3] */
    real ivrc[2], temp;
    real *zpre;
    integer *vwin;
    integer i__, j, lanal;
    real *inbuf, *pebuf;
    real *lpbuf, *ivbuf;
    real *rcbuf;
    integer *osptr;
    integer *osbuf;
    integer ipitch;
    integer *obound;
    integer *voibuf;
    integer mintau;
    real *rmsbuf;
    integer minptr, maxptr;
    real phi[100], psi[10];

    if (speech) {
        --speech;
    }
    if (voice) {
        --voice;
    }
    if (rc) {
        --rc;
    }

    inbuf = &st->inbuf[0];
    pebuf = &st->pebuf[0];
    lpbuf = &st->lpbuf[0];
    ivbuf = &st->ivbuf[0];
    bias = &st->bias;
    osbuf = &st->osbuf[0];
    osptr = &st->osptr;
    obound = &st->obound[0];
    vwin = &st->vwin[0];
    awin = &st->awin[0];
    voibuf = &st->voibuf[0];
    rmsbuf = &st->rmsbuf[0];
    rcbuf = &st->rcbuf[0];
    zpre = &st->zpre;

    /* the analysis runs on the future frame (the pitch tracker needs it); RMS and the RCs are
     * delayed two frames. Shift every buffer by one frame. */
    i__1 = 720 - contrl_.lframe;
    for (i__ = 181; i__ <= i__1; ++i__) {
        inbuf[i__ - 181] = inbuf[contrl_.lframe + i__ - 181];
        pebuf[i__ - 181] = pebuf[contrl_.lframe + i__ - 181];
    }
    i__1 = 540 - contrl_.lframe;
    for (i__ = 229; i__ <= i__1; ++i__) {
        ivbuf[i__ - 229] = ivbuf[contrl_.lframe + i__ - 229];
    }
    i__1 = 720 - contrl_.lframe;
    for (i__ = 25; i__ <= i__1; ++i__) {
        lpbuf[i__ - 25] = lpbuf[contrl_.lframe + i__ - 25];
    }
    j = 1;
    i__1 = *osptr - 1;
    for (i__ = 1; i__ <= i__1; ++i__) {
        if (osbuf[i__ - 1] > contrl_.lframe) {
            osbuf[j - 1] = osbuf[i__ - 1] - contrl_.lframe;
            ++j;
        }
    }
    *osptr = j;
    voibuf[0] = voibuf[2];
    voibuf[1] = voibuf[3];
    for (i__ = 1; i__ <= 2; ++i__) {
        vwin[(i__ << 1) - 2] = vwin[((i__ + 1) << 1) - 2] - contrl_.lframe;
        vwin[(i__ << 1) - 1] = vwin[((i__ + 1) << 1) - 1] - contrl_.lframe;
        awin[(i__ << 1) - 2] = awin[((i__ + 1) << 1) - 2] - contrl_.lframe;
        awin[(i__ << 1) - 1] = awin[((i__ + 1) << 1) - 1] - contrl_.lframe;
        obound[i__ - 1] = obound[i__];
        voibuf[i__ * 2] = voibuf[(i__ + 1) * 2];
        voibuf[(i__ << 1) + 1] = voibuf[((i__ + 1) << 1) + 1];
        rmsbuf[i__ - 1] = rmsbuf[i__];
        i__1 = contrl_.order;
        for (j = 1; j <= i__1; ++j) {
            rcbuf[j + i__ * 10 - 11] = rcbuf[j + (i__ + 1) * 10 - 11];
        }
    }
    /* copy the input scaled to sign + 12 bits, less the long-term DC bias; move the bias by one
     * when the frame's mean is over +-1 */
    temp = 0.f;
    i__1 = contrl_.lframe;
    for (i__ = 1; i__ <= i__1; ++i__) {
        inbuf[720 - contrl_.lframe + i__ - 181] = speech[i__] * 4096.f - *bias;
        temp += inbuf[720 - contrl_.lframe + i__ - 181];
    }
    if (temp > (real)contrl_.lframe) {
        *bias += 1;
    }
    if (temp < (real)(-contrl_.lframe)) {
        *bias += -1;
    }
    /* the voicing window */
    i__ = 721 - contrl_.lframe;
    preemp_(&inbuf[i__ - 181], &pebuf[i__ - 181], &contrl_.lframe, &precoef, zpre);
    onset_(pebuf, osbuf, osptr, &c__10, &c__181, &c__720, &contrl_.lframe, st);
    placev_(osbuf, osptr, &c__10, &obound[2], vwin, &c__3, &contrl_.lframe, &c__90, &c__156,
            &c__307, &c__462);
    /* pitch: AMDF of the low-passed, inverse-filtered signal */
    lpfilt_(&inbuf[228], &lpbuf[384], &c__312, &contrl_.lframe);
    ivfilt_(&lpbuf[204], ivbuf, &c__312, &contrl_.lframe, ivrc);
    tbdm_(ivbuf, &c__156, tau, &c__60, amdf, &minptr, &maxptr, &mintau);
    /* voicing, per half frame */
    for (half = 1; half <= 2; ++half) {
        voicin_(&vwin[4], inbuf, lpbuf, buflim, &half, &amdf[minptr - 1], &amdf[maxptr - 1],
                &mintau, ivrc, obound, voibuf, &c__3, st);
    }
    /* the minimum-cost pitch over several frames */
    dyptrk_(amdf, &c__60, &minptr, &voibuf[7], pitch, &midx, st);
    ipitch = tau[midx - 1];
    /* the analysis and energy windows */
    placea_(&ipitch, voibuf, &obound[2], &c__3, vwin, awin, ewin, &contrl_.lframe, &c__156);
    /* short-term DC bias out of the analysis window, into ABUF */
    lanal = awin[5] + 1 - awin[4];
    dcbias_(&lanal, &pebuf[awin[4] - 181], abuf);
    /* RMS over the energy window (whole pitch periods) */
    i__1 = ewin[5] - ewin[4] + 1;
    energy_(&i__1, &abuf[ewin[4] - awin[4]], &rmsbuf[2]);
    /* covariance matrix, its inversion, and the stability check of the RCs */
    mload_(&contrl_.order, &c__1, &lanal, abuf, phi, psi);
    invert_(&contrl_.order, phi, psi, &rcbuf[20]);
    rcchk_(&contrl_.order, &rcbuf[10], &rcbuf[20]);
    /* the parameters of two frames back */
    voice[1] = voibuf[2];
    voice[2] = voibuf[3];
    *rms = rmsbuf[0];
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        rc[i__] = rcbuf[i__ - 1];
    }
    return 0;
}
