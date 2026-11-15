/* libpttclient chanwr.c (provider): pack the quantised parameters into the 54-bit frame (chanwr_)
 * and unpack them (chanrd_), both entries of one f2c master routine. From the reference ELF; see
 * lpc10.h. */
#include "lpc10.h"

/* 0x3ec850, 888 bytes; bit at 0x43c560, iblist at 0x43c590 (equal to the ELF's data). In the ELF
 * the parameter adjustments are unconditional and chanrd_ passes a null state. */
int chanwr_0_(int n__, integer *order, integer *ipitv, integer *irms, integer *irc,
              integer *ibits, struct lpc10_encoder_state *st)
{
    static integer bit[10] = { 2, 4, 8, 8, 8, 8, 16, 16, 16, 16 };
    static integer iblist[53] = { 13, 12, 11, 1, 2, 13, 12, 11, 1, 2, 13, 10, 11, 2, 1, 10, 13,
        12, 11, 10, 2, 13, 12, 11, 10, 2, 1, 12, 7, 6, 1, 10, 9, 8, 7, 4, 6, 9, 8, 7, 5, 1, 9, 8, 4,
        6, 1, 5, 9, 8, 7, 5, 6 };

    integer i__1;
    integer itab[13], i__;
    integer *isync;

    --irc;
    --ibits;

    switch (n__) {
    case 1:
        goto L_chanrd;
    }

    isync = &st->isync;

    /* place the quantised parameters into the bit table */
    itab[0] = *ipitv;
    itab[1] = *irms;
    itab[2] = 0;
    i__1 = *order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        itab[i__ + 2] = irc[*order + 1 - i__] & 32767;
    }
    /* take the bits from the table in the order of iblist */
    for (i__ = 1; i__ <= 53; ++i__) {
        ibits[i__] = itab[iblist[i__ - 1] - 1] & 1;
        itab[iblist[i__ - 1] - 1] /= 2;
    }
    /* the alternating sync bit */
    ibits[54] = *isync & 1;
    *isync = 1 - *isync;
    return 0;

L_chanrd:
    /* rebuild the table from the bits, last bit first */
    for (i__ = 1; i__ <= 13; ++i__) {
        itab[i__ - 1] = 0;
    }
    for (i__ = 1; i__ <= 53; ++i__) {
        itab[iblist[54 - i__ - 1] - 1] = (itab[iblist[54 - i__ - 1] - 1] << 1) + ibits[54 - i__];
    }
    /* sign-extend the RCs */
    i__1 = *order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        if ((itab[i__ + 2] & bit[i__ - 1]) != 0) {
            itab[i__ + 2] -= bit[i__ - 1] << 1;
        }
    }
    /* restore the variables */
    *ipitv = itab[0];
    *irms = itab[1];
    i__1 = *order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        irc[i__] = itab[*order + 4 - i__ - 1];
    }
    return 0;
}

/* 0x3ecbd0, 88 bytes */
int chanwr_(integer *order, integer *ipitv, integer *irms, integer *irc, integer *ibits,
            struct lpc10_encoder_state *st)
{
    return chanwr_0_(0, order, ipitv, irms, irc, ibits, st);
}

/* 0x3ecc30, 84 bytes */
int chanrd_(integer *order, integer *ipitv, integer *irms, integer *irc, integer *ibits)
{
    return chanwr_0_(1, order, ipitv, irms, irc, ibits, (struct lpc10_encoder_state *)0);
}
