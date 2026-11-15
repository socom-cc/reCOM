/* libpttclient dyptrk.c (provider): dynamic-programming pitch tracker over two frames. State in
 * the encoder record. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3ee180, 1544 bytes */
int dyptrk_(real *amdf, integer *ltau, integer *minptr, integer *voice, integer *pitch,
            integer *midx, struct lpc10_encoder_state *st)
{
    integer i__1;
    integer pbar;
    real sbar;
    integer path[2], iptr, i__, j;
    real alpha, minsc, maxsc;
    real *s;
    integer *p;
    integer *ipoint;
    real *alphax;

    s = &st->s[0];
    p = &st->p[0];
    ipoint = &st->ipoint;
    alphax = &st->alphax;

    if (amdf) {
        --amdf;
    }

    /* the pitch-change penalty ALPHA follows the AMDF minimum of voiced frames */
    if (*voice == 1) {
        *alphax = *alphax * .75f + amdf[*minptr] / 2.f;
    } else {
        *alphax *= .984375f;
    }
    alpha = *alphax / 16;
    if (*voice == 0 && *alphax < 128.f) {
        alpha = 8.f;
    }
    /* SEESAW: pitch pointer array and intermediate winner function, left to right */
    iptr = *ipoint + 1;
    p[iptr * 60 - 60] = 1;
    i__ = 1;
    pbar = 1;
    sbar = s[0];
    i__1 = *ltau;
    for (i__ = 1; i__ <= i__1; ++i__) {
        sbar += alpha;
        if (sbar < s[i__ - 1]) {
            s[i__ - 1] = sbar;
            p[i__ + iptr * 60 - 61] = pbar;
        } else {
            sbar = s[i__ - 1];
            p[i__ + iptr * 60 - 61] = i__;
            pbar = i__;
        }
    }
    /* right to left */
    i__ = pbar - 1;
    sbar = s[i__ - 1];
    while (i__ >= 1) {
        sbar += alpha;
        if (sbar < s[i__ - 1]) {
            s[i__ - 1] = sbar;
            p[i__ + iptr * 60 - 61] = pbar;
        } else {
            pbar = p[i__ + iptr * 60 - 61];
            i__ = pbar;
            sbar = s[i__ - 1];
        }
        --i__;
    }
    /* update S with the AMDF; maximum, minimum and where the minimum is */
    s[0] += amdf[1] / 2;
    minsc = s[0];
    maxsc = minsc;
    *midx = 1;
    i__1 = *ltau;
    for (i__ = 2; i__ <= i__1; ++i__) {
        s[i__ - 1] += amdf[i__] / 2;
        if (s[i__ - 1] > maxsc) {
            maxsc = s[i__ - 1];
        }
        if (s[i__ - 1] < minsc) {
            *midx = i__;
            minsc = s[i__ - 1];
        }
    }
    /* subtract MINSC to keep S from growing */
    i__1 = *ltau;
    for (i__ = 1; i__ <= i__1; ++i__) {
        s[i__ - 1] -= minsc;
    }
    maxsc -= minsc;
    /* take the higher octave if it has a significant null */
    j = 0;
    for (i__ = 20; i__ <= 40; i__ += 10) {
        if (*midx > i__) {
            if (s[*midx - i__ - 1] < maxsc / 4) {
                j = i__;
            }
        }
    }
    *midx -= j;
    /* trace back two frames for the minimum-cost pitch */
    j = *ipoint;
    *pitch = *midx;
    for (i__ = 1; i__ <= 2; ++i__) {
        j = j % 2 + 1;
        *pitch = p[*pitch + j * 60 - 61];
        path[i__ - 1] = *pitch;
    }
    *ipoint = (*ipoint + 1) % 2;
    (void)path;
    return 0;
}
