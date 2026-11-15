/* libpttclient irc2pc.c (provider): reflection coefficients to predictor coefficients. From the
 * reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3efa20, 536 bytes. The square root is single precision (sqrtf) in the ELF. */
int irc2pc_(real *rc, real *pc, integer *order, real *gprime, real *g2pass)
{
    integer i__1, i__2;
    real temp[10];
    integer i__, j;

    --pc;
    --rc;

    *g2pass = 1.f;
    i__1 = *order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        *g2pass *= 1.f - rc[i__] * rc[i__];
    }
    *g2pass = *gprime * sqrtf(*g2pass);
    pc[1] = rc[1];
    i__1 = *order;
    for (i__ = 2; i__ <= i__1; ++i__) {
        i__2 = i__ - 1;
        for (j = 1; j <= i__2; ++j) {
            temp[j - 1] = pc[j] - rc[i__] * pc[i__ - j];
        }
        i__2 = i__ - 1;
        for (j = 1; j <= i__2; ++j) {
            pc[j] = temp[j - 1];
        }
        pc[i__] = rc[i__];
    }
    return 0;
}
