/* libpttclient synths.c (provider): synthesise one frame: interpolate the parameters per pitch
 * period (pitsyn_), convert to predictor coefficients, excite and filter (bsynz_), de-emphasise,
 * and hand out 180 samples. State in the decoder record. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

static real c_b2 = 0x1.666666p-1f /* .699999988 */; /* 0x4755c4, the word 0x3f333333 */

/* 0x3f4b10, 1040 bytes. .99 is the ELF's 0x3f7d70a4. */
int synths_(integer *voice, integer *pitch, real *rms, real *rc, real *speech, integer *k,
            struct lpc10_decoder_state *st)
{
    integer i__1;
    real r__1, r__2;
    real rmsi[16];
    integer nout, ivuv[16], i__, j;
    real ratio;
    integer ipiti[16];
    real g2pass;
    real pc[10];
    real rci[160]; /* was [10][16] */
    real *buf;
    integer *buflen;

    if (voice) {
        --voice;
    }
    if (rc) {
        --rc;
    }
    if (speech) {
        --speech;
    }

    buf = &st->buf[0];
    buflen = &st->buflen;

    i__1 = min(*pitch, 156);
    *pitch = max(i__1, 20);
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        r__2 = rc[i__];
        r__1 = min(r__2, 0x1.fae148p-1f /* .99000001 */);
        rc[i__] = max(r__1, -0x1.fae148p-1f /* .99000001 */);
    }
    pitsyn_(&contrl_.order, &voice[1], pitch, rms, &rc[1], &contrl_.lframe, ivuv, ipiti, rmsi, rci,
            &nout, &ratio, st);
    if (nout > 0) {
        i__1 = nout;
        for (j = 1; j <= i__1; ++j) {
            /* one pitch period of speech onto the end of BUF */
            irc2pc_(&rci[j * 10 - 10], pc, &contrl_.order, &c_b2, &g2pass);
            bsynz_(pc, &ipiti[j - 1], &ivuv[j - 1], &buf[*buflen], &rmsi[j - 1], &ratio, &g2pass,
                   st);
            deemp_(&buf[*buflen], &ipiti[j - 1], st);
            *buflen += ipiti[j - 1];
        }
        /* the first 180 samples out (scaled), and off the front of BUF */
        for (i__ = 1; i__ <= 180; ++i__) {
            speech[i__] = buf[i__ - 1] / 4096.f;
        }
        *k = 180;
        *buflen += -180;
        i__1 = *buflen;
        for (i__ = 1; i__ <= i__1; ++i__) {
            buf[i__ - 1] = buf[i__ + 179];
        }
    }
    return 0;
}
