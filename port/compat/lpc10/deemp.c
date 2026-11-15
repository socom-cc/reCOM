/* libpttclient deemp.c (provider): de-emphasis filter of the synthesised speech, state in the
 * decoder record. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3edd80, 400 bytes. Constants as the ELF's words: 1.9998 (0x3ffff972), 2.5, 2.0925
 * (0x4005eb85), .585 (0x3f15c28f). */
int deemp_(real *x, integer *n, struct lpc10_decoder_state *st)
{
    integer i__1;
    real r__1;
    integer k;
    real dei0;
    real *dei1, *dei2, *deo1, *deo2, *deo3;

    if (x) {
        --x;
    }

    dei1 = &st->dei1;
    dei2 = &st->dei2;
    deo1 = &st->deo1;
    deo2 = &st->deo2;
    deo3 = &st->deo3;

    i__1 = *n;
    for (k = 1; k <= i__1; ++k) {
        dei0 = x[k];
        r__1 = x[k] - *dei1 * 0x1.fff2e4p0f /* 1.99979997 */ + *dei2;
        x[k] = r__1 + *deo1 * 2.5f - *deo2 * 0x1.0bd70ap1f /* 2.09249997 */ + *deo3 * 0x1.2b851ep-1f /* .584999979 */;
        *dei2 = *dei1;
        *dei1 = dei0;
        *deo3 = *deo2;
        *deo2 = *deo1;
        *deo1 = x[k];
    }
    return 0;
}
