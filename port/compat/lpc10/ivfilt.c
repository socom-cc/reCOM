/* libpttclient ivfilt.c (provider): 2nd-order inverse filter of the 4:1 decimated low-passed
 * speech (for the voicing/pitch analysis). From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3efc40, 660 bytes. 1e-10 is the ELF's 0x2edbe6ff. */
int ivfilt_(real *lpbuf, real *ivbuf, integer *len, integer *nsamp, real *ivrc)
{
    integer i__1;
    integer i__, j, k;
    real r__[3], pc1, pc2;

    --ivrc;
    --ivbuf;
    --lpbuf;

    /* autocorrelations at lags 0, 4 and 8 of every other sample */
    for (j = 1; j <= 3; ++j) {
        r__[j - 1] = 0.f;
        k = (j - 1) << 2;
        i__1 = *len;
        for (i__ = (j << 2) + *len - *nsamp; i__ <= i__1; i__ += 2) {
            r__[j - 1] += lpbuf[i__] * lpbuf[i__ - k];
        }
    }
    /* predictor coefficients */
    pc1 = 0.f;
    pc2 = 0.f;
    ivrc[1] = 0.f;
    ivrc[2] = 0.f;
    if (r__[0] > 0x1.b7cdfep-34f /* 1e-10 */) {
        ivrc[1] = r__[1] / r__[0];
        ivrc[2] = (r__[2] - ivrc[1] * r__[1]) / (r__[0] - ivrc[1] * r__[1]);
        pc1 = ivrc[1] - ivrc[1] * ivrc[2];
        pc2 = ivrc[2];
    }
    /* inverse filter */
    i__1 = *len;
    for (i__ = *len + 1 - *nsamp; i__ <= i__1; ++i__) {
        ivbuf[i__] = lpbuf[i__] - pc1 * lpbuf[i__ - 4] - pc2 * lpbuf[i__ - 8];
    }
    return 0;
}
