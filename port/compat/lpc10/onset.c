/* libpttclient onset.c (provider): onset detection on the pre-emphasised speech (first-order
 * predictor coefficient FPC, slope over 8 samples). From the reference ELF; see lpc10.h. */
#include "lpc10.h"

static real c_b2 = 1.f; /* 0x4755bc */

/* 0x3f2670, 1168 bytes. 1.7 is the ELF's 0x3fd9999a. */
int onset_(real *pebuf, integer *osbuf, integer *osptr, integer *oslen, integer *sbufl,
           integer *sbufh, integer *lframe, struct lpc10_encoder_state *st)
{
    integer pebuf_offset, i__1;
    real r__1;
    integer i__;
    real l2sum2;
    real *n, *d__, *fpc, *l2buf, *l2sum1;
    integer *l2ptr1, *l2ptr2, *lasti;
    logical *hyst;

    n = &st->n;
    d__ = &st->d__;
    fpc = &st->fpc;
    l2buf = &st->l2buf[0];
    l2sum1 = &st->l2sum1;
    l2ptr1 = &st->l2ptr1;
    l2ptr2 = &st->l2ptr2;
    lasti = &st->lasti;
    hyst = &st->hyst;

    if (osbuf) {
        --osbuf;
    }
    if (pebuf) {
        pebuf_offset = *sbufl;
        pebuf -= pebuf_offset;
    }

    if (*hyst) {
        *lasti -= *lframe;
    }
    i__1 = *sbufh;
    for (i__ = *sbufh - *lframe + 1; i__ <= i__1; ++i__) {
        /* the first-order predictor coefficient FPC = N / D */
        *n = (pebuf[i__] * pebuf[i__ - 1] + *n * 63.f) / 64.f;
        r__1 = pebuf[i__ - 1];
        *d__ = (r__1 * r__1 + *d__ * 63.f) / 64.f;
        if (*d__ != 0.f) {
            if (abs(*n) > *d__) {
                *fpc = r_sign(&c_b2, n);
            } else {
                *fpc = *n / *d__;
            }
        }
        /* its slope over 8 samples, from two running sums */
        l2sum2 = l2buf[*l2ptr1 - 1];
        *l2sum1 = *l2sum1 - l2buf[*l2ptr2 - 1] + *fpc;
        l2buf[*l2ptr2 - 1] = *l2sum1;
        l2buf[*l2ptr1 - 1] = *fpc;
        *l2ptr1 = *l2ptr1 % 16 + 1;
        *l2ptr2 = *l2ptr2 % 16 + 1;
        if ((r__1 = *l2sum1 - l2sum2, abs(r__1)) > 0x1.b33334p0f /* 1.70000005 */) {
            if (!(*hyst)) {
                /* an onset, 9 samples back */
                if (*osptr <= *oslen) {
                    osbuf[*osptr] = i__ - 9;
                    ++(*osptr);
                }
                *hyst = TRUE_;
            }
            *lasti = i__;
        } else if (*hyst && i__ - *lasti >= 10) {
            *hyst = FALSE_;
        }
    }
    return 0;
}
