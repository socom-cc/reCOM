/* libpttclient bsynz.c (provider): synthesise one pitch period: pulse (voiced) or noise and
 * doublet (unvoiced) excitation, the all-zero and all-pole LPC filters, gain to the RMS. State in
 * the decoder record. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3ebe70, 2524 bytes; kexc at 0x43c4f0 (equal to the ELF's data). 1e-6 is 0x358637bd, 6.928
 * is 0x40ddb22d; the square roots are single precision (sqrtf). The ELF's excitation filters
 * have no third tap (the public coder adds lpi3 * 0 and hpi3 * 0), and its scalings by 1 are
 * absent. */
int bsynz_(real *coef, integer *ip, integer *iv, real *sout, real *rms, real *ratio, real *g2pass,
           struct lpc10_decoder_state *st)
{
    static integer kexc[25] = { 8, -16, 26, -48, 86, -162, 294, -502, 718, -728, 184, 672, -610,
        -672, 184, 728, 718, 502, 294, 162, 86, 48, 26, 16, 8 };

    integer i__1, i__2;
    real r__1, r__2;
    real gain, xssq;
    integer i__, j, k;
    real noise[166], pulse;
    integer px;
    real sscale;
    real xy, sum, ssq;
    real lpi0, hpi0;
    integer *ipo;
    real *exc, *exc2, *lpi1, *lpi2, *lpi3, *hpi1, *hpi2, *hpi3, *rmso;

    if (coef) {
        --coef;
    }
    if (sout) {
        --sout;
    }

    ipo = &st->ipo;
    exc = &st->exc[0];
    exc2 = &st->exc2[0];
    lpi1 = &st->lpi1;
    lpi2 = &st->lpi2;
    lpi3 = &st->lpi3;
    hpi1 = &st->hpi1;
    hpi2 = &st->hpi2;
    hpi3 = &st->hpi3;
    rmso = &st->rmso_bsynz;

    /* history scale factor XY, applied to the filter state */
    r__1 = *rmso / (*rms + 0x1.0c6f7ap-20f /* 1e-6 */);
    xy = min(r__1, 8.f);
    *rmso = *rms;
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        exc2[i__ - 1] = exc2[*ipo + i__ - 1] * xy;
    }
    *ipo = *ip;
    if (*iv == 0) {
        /* unvoiced: white noise ... */
        i__1 = *ip;
        for (i__ = 1; i__ <= i__1; ++i__) {
            exc[contrl_.order + i__ - 1] = (real)(random_(st) / 64);
        }
        /* ... plus an impulse doublet for plosives; (random + 32768) is 0 .. 65535 */
        px = (random_(st) + 32768) * (*ip - 1) / 65536 + contrl_.order + 1;
        r__1 = *ratio / 4;
        pulse = r__1 * 342;
        if (pulse > 2e3f) {
            pulse = 2e3f;
        }
        exc[px - 1] += pulse;
        exc[px] -= pulse;
    } else {
        /* voiced: the pulse KEXC, low-passed, plus high-passed noise */
        sscale = sqrtf((real)(*ip)) / 0x1.bb645ap2f /* 6.92799997 */;
        i__1 = *ip;
        for (i__ = 1; i__ <= i__1; ++i__) {
            exc[contrl_.order + i__ - 1] = 0.f;
            if (i__ <= 25) {
                exc[contrl_.order + i__ - 1] = sscale * kexc[i__ - 1];
            }
            lpi0 = exc[contrl_.order + i__ - 1];
            r__2 = exc[contrl_.order + i__ - 1] * .125f + *lpi1 * .75f;
            r__1 = r__2 + *lpi2 * .125f;
            exc[contrl_.order + i__ - 1] = r__1;
            *lpi3 = *lpi2;
            *lpi2 = *lpi1;
            *lpi1 = lpi0;
        }
        i__1 = *ip;
        for (i__ = 1; i__ <= i__1; ++i__) {
            noise[contrl_.order + i__ - 1] = (real)random_(st) / 64;
            hpi0 = noise[contrl_.order + i__ - 1];
            r__2 = noise[contrl_.order + i__ - 1] * -.125f + *hpi1 * .25f;
            r__1 = r__2 + *hpi2 * -.125f;
            noise[contrl_.order + i__ - 1] = r__1;
            *hpi3 = *hpi2;
            *hpi2 = *hpi1;
            *hpi1 = hpi0;
        }
        i__1 = *ip;
        for (i__ = 1; i__ <= i__1; ++i__) {
            exc[contrl_.order + i__ - 1] += noise[contrl_.order + i__ - 1];
        }
    }
    /* all-zero filter 1 + G * SUM */
    xssq = 0.f;
    i__1 = *ip;
    for (i__ = 1; i__ <= i__1; ++i__) {
        k = contrl_.order + i__;
        sum = 0.f;
        i__2 = contrl_.order;
        for (j = 1; j <= i__2; ++j) {
            sum += coef[j] * exc[k - j - 1];
        }
        sum *= *g2pass;
        exc2[k - 1] = sum + exc[k - 1];
    }
    /* all-pole filter 1 / (1 - SUM) */
    i__1 = *ip;
    for (i__ = 1; i__ <= i__1; ++i__) {
        k = contrl_.order + i__;
        sum = 0.f;
        i__2 = contrl_.order;
        for (j = 1; j <= i__2; ++j) {
            sum += coef[j] * exc2[k - j - 1];
        }
        exc2[k - 1] = sum + exc2[k - 1];
        xssq += exc2[k - 1] * exc2[k - 1];
    }
    /* filter history for the next epoch */
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        exc[i__ - 1] = exc[*ip + i__ - 1];
        exc2[i__ - 1] = exc2[*ip + i__ - 1];
    }
    /* gain to the RMS */
    r__1 = *rms * *rms;
    ssq = r__1 * *ip;
    gain = sqrtf(ssq / xssq);
    i__1 = *ip;
    for (i__ = 1; i__ <= i__1; ++i__) {
        sout[i__] = gain * exc2[contrl_.order + i__ - 1];
    }
    return 0;
}
