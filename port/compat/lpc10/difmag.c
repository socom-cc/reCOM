/* libpttclient difmag.c (provider): average magnitude difference function for the pitch
 * search. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3edf10, 612 bytes */
int difmag_(real *speech, integer *lpita, integer *tau, integer *ltau, integer *maxlag,
            real *amdf, integer *minptr, integer *maxptr)
{
    integer i__1, i__2;
    real r__1;
    integer i__, j, n1, n2;
    real sum;

    --amdf;
    --tau;
    --speech;

    *minptr = 1;
    *maxptr = 1;
    i__1 = *ltau;
    for (i__ = 1; i__ <= i__1; ++i__) {
        n1 = (*maxlag - tau[i__]) / 2 + 1;
        n2 = n1 + *lpita - 1;
        sum = 0.f;
        i__2 = n2;
        for (j = n1; j <= i__2; j += 4) {
            sum += (r__1 = speech[j] - speech[j + tau[i__]], abs(r__1));
        }
        amdf[i__] = sum;
        if (amdf[i__] < amdf[*minptr]) {
            *minptr = i__;
        }
        if (amdf[i__] > amdf[*maxptr]) {
            *maxptr = i__;
        }
    }
    return 0;
}
