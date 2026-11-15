/* libpttclient vparms.c (provider): the voicing parameters of one half frame (zero crossings,
 * low-band and full-band energy, first-difference energy ratio, unit-delay correlation and the
 * forward / backward prediction gains at the pitch lag). From the reference ELF; see lpc10.h. */
#include "lpc10.h"

static real c_b2 = 1.f; /* 0x4755c8 */

/* 0x3f6090, 2184 bytes */
int vparms_(integer *vwin, real *inbuf, real *lpbuf, integer *buflim, integer *half, real *dither,
            integer *mintau, integer *zc, integer *lbe, integer *fbe, real *qs, real *rc1,
            real *ar_b__, real *ar_f__)
{
    integer inbuf_offset, lpbuf_offset, i__1;
    real r__1, r__2;
    integer vlen, stop, i__;
    real e_pre__;
    integer start;
    real ap_rms__, e_0__, oldsgn, lp_rms__, e_b__, e_f__, r_b__, r_f__, e0ap;

    --vwin;
    --buflim;
    lpbuf_offset = buflim[3];
    lpbuf -= lpbuf_offset;
    inbuf_offset = buflim[1];
    inbuf -= inbuf_offset;

    lp_rms__ = 0.f;
    ap_rms__ = 0.f;
    e_pre__ = 0.f;
    e0ap = 0.f;
    *rc1 = 0.f;
    e_0__ = 0.f;
    e_b__ = 0.f;
    e_f__ = 0.f;
    r_f__ = 0.f;
    r_b__ = 0.f;
    *zc = 0;
    vlen = vwin[2] - vwin[1] + 1;
    start = vwin[1] + (*half - 1) * vlen / 2 + 1;
    stop = start + vlen / 2 - 1;

    r__1 = inbuf[start - 1] - *dither;
    oldsgn = r_sign(&c_b2, &r__1);
    i__1 = stop;
    for (i__ = start; i__ <= i__1; ++i__) {
        lp_rms__ += (r__1 = lpbuf[i__], abs(r__1));
        ap_rms__ += (r__1 = inbuf[i__], abs(r__1));
        e_pre__ += (r__1 = inbuf[i__] - inbuf[i__ - 1], abs(r__1));
        r__1 = inbuf[i__];
        e0ap += r__1 * r__1;
        *rc1 += inbuf[i__] * inbuf[i__ - 1];
        r__1 = lpbuf[i__];
        e_0__ += r__1 * r__1;
        r__1 = lpbuf[i__ - *mintau];
        e_b__ += r__1 * r__1;
        r__1 = lpbuf[i__ + *mintau];
        e_f__ += r__1 * r__1;
        r_f__ += lpbuf[i__] * lpbuf[i__ + *mintau];
        r_b__ += lpbuf[i__] * lpbuf[i__ - *mintau];
        r__1 = inbuf[i__] + *dither;
        if (r_sign(&c_b2, &r__1) != oldsgn) {
            ++(*zc);
            oldsgn = -oldsgn;
        }
        *dither = -(*dither);
    }
    /* normalised autocovariance at unit delay */
    *rc1 /= max(e0ap, 1.f);
    /* first-difference to full-band energy ratio */
    r__1 = ap_rms__ * 2.f;
    *qs = e_pre__ / max(r__1, 1.f);
    /* prediction gains of the low-passed signal at the pitch lag, backward and forward */
    *ar_b__ = r_b__ / max(e_b__, 1.f) * (r_b__ / max(e_0__, 1.f));
    *ar_f__ = r_f__ / max(e_f__, 1.f) * (r_f__ / max(e_0__, 1.f));
    /* ZC, LBE and FBE normalised to the old fixed window of 180 */
    r__2 = (real)(*zc << 1);
    r__1 = r__2 * (90.f / vlen);
    *zc = i_nint(&r__1);
    r__1 = lp_rms__ / 4 * (90.f / vlen);
    i__1 = i_nint(&r__1);
    *lbe = min(i__1, 32767);
    r__1 = ap_rms__ / 4 * (90.f / vlen);
    i__1 = i_nint(&r__1);
    *fbe = min(i__1, 32767);
    return 0;
}
