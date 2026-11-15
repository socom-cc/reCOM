/* libpttclient tbdm.c (provider): time-domain pitch search, coarse AMDF then the lags around
 * its minimum and one octave up. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f4f20, 1292 bytes. minamd is an integer (the ELF converts with fptosi, truncating). */
int tbdm_(real *speech, integer *lpita, integer *tau, integer *ltau, real *amdf, integer *minptr,
          integer *maxptr, integer *mintau)
{
    integer i__1, i__2, i__3, i__4;
    real amdf2[6];
    integer minp2, ltau2, maxp2, i__;
    integer minamd, ptr, tau2[6];

    --speech;
    --amdf;
    --tau;

    /* coarse AMDF over all lags */
    difmag_(&speech[1], lpita, &tau[1], ltau, &tau[*ltau], &amdf[1], minptr, maxptr);
    *mintau = tau[*minptr];
    minamd = amdf[*minptr];
    /* all lags within +/- 3 of the minimum not computed yet */
    ltau2 = 0;
    ptr = *minptr - 2;
    i__1 = *mintau - 3;
    i__3 = *mintau + 3, i__4 = tau[*ltau] - 1;
    i__2 = min(i__3, i__4);
    for (i__ = max(i__1, 41); i__ <= i__2; ++i__) {
        while (tau[ptr] < i__) {
            ++ptr;
        }
        if (tau[ptr] != i__) {
            ++ltau2;
            tau2[ltau2 - 1] = i__;
        }
    }
    /* their AMDF; take the best if it beats the coarse minimum */
    if (ltau2 > 0) {
        difmag_(&speech[1], lpita, tau2, &ltau2, &tau[*ltau], amdf2, &minp2, &maxp2);
        if (amdf2[minp2 - 1] < (real)minamd) {
            *mintau = tau2[minp2 - 1];
            minamd = amdf2[minp2 - 1];
        }
    }
    /* one octave up */
    if (*mintau >= 80) {
        i__ = *mintau / 2;
        if ((i__ & 1) == 0) {
            ltau2 = 2;
            tau2[0] = i__ - 1;
            tau2[1] = i__ + 1;
        } else {
            ltau2 = 1;
            tau2[0] = i__;
        }
        difmag_(&speech[1], lpita, tau2, &ltau2, &tau[*ltau], amdf2, &minp2, &maxp2);
        if (amdf2[minp2 - 1] < (real)minamd) {
            *mintau = tau2[minp2 - 1];
            minamd = amdf2[minp2 - 1];
            *minptr += -20;
        }
    }
    /* the AMDF minimum takes the high-resolution value */
    amdf[*minptr] = (real)minamd;
    /* the maximum within half an octave of the minimum */
    i__2 = *minptr - 5;
    *maxptr = max(i__2, 1);
    i__1 = *minptr + 5;
    i__2 = min(i__1, *ltau);
    for (i__ = *maxptr + 1; i__ <= i__2; ++i__) {
        if (amdf[i__] > amdf[*maxptr]) {
            *maxptr = i__;
        }
    }
    return 0;
}
