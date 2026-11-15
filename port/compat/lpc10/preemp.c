/* libpttclient preemp.c (provider): first-order pre-emphasis filter. From the reference ELF; see
 * lpc10.h. */
#include "lpc10.h"

/* 0x3f47c0, 204 bytes */
int preemp_(real *inbuf, real *pebuf, integer *nsamp, real *coef, real *z__)
{
    integer i__1;
    real temp;
    integer i__;

    --pebuf;
    --inbuf;

    i__1 = *nsamp;
    for (i__ = 1; i__ <= i__1; ++i__) {
        temp = inbuf[i__] - *coef * *z__;
        *z__ = inbuf[i__];
        pebuf[i__] = temp;
    }
    return 0;
}
