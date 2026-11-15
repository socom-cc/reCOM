/* libpttclient dcbias.c (provider): remove the mean of a buffer. From the reference ELF; see
 * lpc10.h. */
#include "lpc10.h"

/* 0x3ecc90, 260 bytes */
int dcbias_(integer *len, real *speech, real *sigout)
{
    integer i__1;
    integer i__;
    real bias;

    --sigout;
    --speech;

    bias = 0.f;
    i__1 = *len;
    for (i__ = 1; i__ <= i__1; ++i__) {
        bias += speech[i__];
    }
    bias /= *len;
    i__1 = *len;
    for (i__ = 1; i__ <= i__1; ++i__) {
        sigout[i__] = speech[i__] - bias;
    }
    return 0;
}
