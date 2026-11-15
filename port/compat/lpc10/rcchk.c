/* libpttclient rcchk.c (provider): reject an unstable set of reflection coefficients. From the
 * reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f49d0, 316 bytes: if any |rc2f| > .99 (0x3f7d70a4), rc2f takes the previous frame's rc1f. */
int rcchk_(integer *order, real *rc1f, real *rc2f)
{
    integer i__1;
    real r__1;
    integer i__;

    --rc2f;
    --rc1f;

    i__1 = *order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        if ((r__1 = rc2f[i__], abs(r__1)) > 0x1.fae148p-1f /* .99 */) {
            goto L10;
        }
    }
    return 0;
L10:
    i__1 = *order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        rc2f[i__] = rc1f[i__];
    }
    return 0;
}
