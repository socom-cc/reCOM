/* libpttclient voicin.c (provider): voicing detection, a linear discriminant of the voicing
 * parameters per half frame with an SNR-dependent coefficient set, then smoothing of the
 * decisions. State in the encoder record. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f5430, 3164 bytes; vdc at 0x43d160, vdcl at 0x43d2f0 (equal to the ELF's data). nvdcl is a
 * .sbss word set to 5 on the first call under an init$18 guard in the ELF; a plain initialised
 * static here. The smoothing switch follows the ELF's jump table at 0x4679c0. af (the 12th
 * argument, &c__3 from analys_) is not read: the ELF never loads it and its DWARF names no such
 * parameter. */
int voicin_(integer *vwin, real *inbuf, real *lpbuf, integer *buflim, integer *half,
            real *minamd, real *maxamd, integer *mintau, real *ivrc, integer *obound,
            integer *voibuf, integer *af, struct lpc10_encoder_state *st)
{
    static integer nvdcl = 5;
    static real vdcl[10] = { 600.f, 450.f, 300.f, 200.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f };
    static real vdc[100] = { /* was [10][10] */
        0.f, 1714.f, -110.f, 334.f, -4096.f, -654.f, 3752.f, 3769.f, 0.f, 1181.f,
        0.f, 874.f, -97.f, 300.f, -4096.f, -1021.f, 2451.f, 2527.f, 0.f, -500.f,
        0.f, 510.f, -70.f, 250.f, -4096.f, -1270.f, 2194.f, 2491.f, 0.f, -1500.f,
        0.f, 500.f, -10.f, 200.f, -4096.f, -1300.f, 2000.f, 2000.f, 0.f, -2000.f,
        0.f, 500.f, 0.f, 0.f, -4096.f, -1300.f, 2000.f, 2000.f, 0.f, -2500.f,
        0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f,
        0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f,
        0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f,
        0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f,
        0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.f };

    integer inbuf_offset = 0, lpbuf_offset = 0, i__1, i__2;
    real r__1, r__2;
    real ar_b__, ar_f__;
    integer snrl, i__;
    integer vstate;
    real snr2;
    integer zc;
    logical ot;
    integer lbe, fbe;
    real qs, rc1;
    real value[9];
    real *dither, *snr, *maxmin, *voice;
    integer *lbve, *lbue, *fbve, *fbue, *ofbue, *sfbue, *olbue, *slbue;

    dither = &st->dither;
    snr = &st->snr;
    maxmin = &st->maxmin;
    voice = &st->voice[0];
    lbve = &st->lbve;
    lbue = &st->lbue;
    fbve = &st->fbve;
    fbue = &st->fbue;
    ofbue = &st->ofbue;
    olbue = &st->olbue;
    sfbue = &st->sfbue;
    slbue = &st->slbue;

    if (vwin) {
        --vwin;
    }
    if (buflim) {
        --buflim;
    }
    if (inbuf) {
        inbuf_offset = buflim[1];
        inbuf -= inbuf_offset;
    }
    if (lpbuf) {
        lpbuf_offset = buflim[3];
        lpbuf -= lpbuf_offset;
    }
    if (ivrc) {
        --ivrc;
    }
    if (obound) {
        --obound;
    }
    if (voibuf) {
        --voibuf;
    }

    /* shift the discriminant history once per frame */
    if (*half == 1) {
        voice[0] = voice[2];
        voice[1] = voice[3];
        voice[2] = voice[4];
        voice[3] = voice[5];
        *maxmin = *maxamd / max(*minamd, 1.f);
    }
    /* the voicing parameters, twice per frame */
    vparms_(&vwin[1], &inbuf[inbuf_offset], &lpbuf[lpbuf_offset], &buflim[1], half, dither, mintau,
            &zc, &lbe, &fbe, &qs, &rc1, &ar_b__, &ar_f__);
    /* SNR estimate (running average of voiced over unvoiced full-band energy, gain 63) */
    r__1 = (*snr + *fbve / (real)max(*fbue, 1)) * 63 / 64.f;
    *snr = (real)i_nint(&r__1);
    snr2 = *snr * *fbue / max(*lbue, 1);
    /* quantise it to SNRL by the VDCL thresholds */
    snrl = 1;
    i__1 = nvdcl - 1;
    for (snrl = 1; snrl <= i__1; ++snrl) {
        if (snr2 > vdcl[snrl - 1]) {
            goto L69;
        }
    }
L69:
    /* the linear discriminant */
    value[0] = *maxmin;
    value[1] = (real)lbe / max(*lbve, 1);
    value[2] = (real)zc;
    value[3] = rc1;
    value[4] = qs;
    value[5] = ivrc[2];
    value[6] = ar_b__;
    value[7] = ar_f__;
    voice[*half + 3] = vdc[snrl * 10 - 1];
    for (i__ = 1; i__ <= 8; ++i__) {
        voice[*half + 3] += vdc[i__ + snrl * 10 - 11] * value[i__ - 1];
    }
    /* voiced if the discriminant is positive */
    if (voice[*half + 3] > 0.f) {
        voibuf[*half + 6] = 1;
    } else {
        voibuf[*half + 6] = 0;
    }
    /* no smoothing in the first half frame */
    vstate = -1;
    if (*half == 1) {
        goto L99;
    }
    /* onset transition: an onset bounds the voicing window in this frame */
    ot = ((obound[1] & 2) != 0 || obound[2] == 1) && (obound[3] & 1) == 0;
    /* dispatch on the decision history P1 P2 C1 C2 */
    vstate = (voibuf[3] << 3) + (voibuf[4] << 2) + (voibuf[5] << 1) + voibuf[6];
    switch (vstate + 1) {
    case 1:
        goto L99;
    case 2:
        goto L1;
    case 3:
        goto L2;
    case 4:
        goto L99;
    case 5:
        goto L4;
    case 6:
        goto L5;
    case 7:
        goto L6;
    case 8:
        goto L7;
    case 9:
        goto L8;
    case 10:
        goto L99;
    case 11:
        goto L10;
    case 12:
        goto L11;
    case 13:
        goto L99;
    case 14:
        goto L12;
    case 15:
        goto L13;
    case 16:
        goto L99;
    }
L1:
    if (ot && voibuf[7] == 1) {
        voibuf[5] = 1;
    }
    goto L99;
L2:
    if (voibuf[7] == 0 || voice[2] < -voice[3]) {
        voibuf[5] = 0;
    } else {
        voibuf[6] = 1;
    }
    goto L99;
L4:
    voibuf[4] = 0;
    goto L99;
L5:
    if (voice[1] < -voice[2]) {
        voibuf[4] = 0;
    } else {
        voibuf[5] = 1;
    }
    goto L99;
L6:
    if (voibuf[1] == 1 || voibuf[7] == 1 || voice[3] > voice[0]) {
        voibuf[6] = 1;
    } else {
        voibuf[3] = 1;
    }
    goto L99;
L7:
    if (ot) {
        voibuf[4] = 0;
    }
    goto L99;
L8:
    if (ot) {
        voibuf[4] = 1;
    }
    goto L99;
L10:
    if (voice[2] < -voice[1]) {
        voibuf[5] = 0;
    } else {
        voibuf[4] = 1;
    }
    goto L99;
L11:
    voibuf[4] = 1;
    goto L99;
L12:
    if (voibuf[7] == 0 && voice[3] < -voice[2]) {
        voibuf[6] = 0;
    } else {
        voibuf[5] = 1;
    }
    goto L99;
L13:
    if (ot && voibuf[7] == 0) {
        voibuf[5] = 0;
    }
    goto L99;
L99:
    /* update the running energies of the class just decided */
    if (voibuf[*half + 6] == 0) {
        i__1 = fbe, i__2 = *ofbue * 3;
        r__1 = (*sfbue * 63 + (min(i__1, i__2) << 3)) / 64.f;
        *sfbue = i_nint(&r__1);
        *fbue = *sfbue / 8;
        *ofbue = fbe;
        i__1 = lbe, i__2 = *olbue * 3;
        r__1 = (*slbue * 63 + (min(i__1, i__2) << 3)) / 64.f;
        *slbue = i_nint(&r__1);
        *lbue = *slbue / 8;
        *olbue = lbe;
    } else {
        r__1 = (*lbve * 63 + lbe) / 64.f;
        *lbve = i_nint(&r__1);
        r__1 = (*fbve * 63 + fbe) / 64.f;
        *fbve = i_nint(&r__1);
    }
    /* dither threshold for the zero-crossing count (square root in single precision) */
    r__2 = sqrtf((real)(*lbue * *lbve)) * 64 / 3000;
    r__1 = max(r__2, 1.f);
    *dither = min(r__1, 20.f);
    (void)vstate;
    (void)af;
    return 0;
}
