/* libpttclient ham84.c (provider): Hamming (8,4) decoder with error count. From the reference
 * ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3ef230, 308 bytes; dactab at 0x43cf60 (128 words, equal to the ELF's data) */
int ham84_(integer *input, integer *output, integer *errcnt)
{
    static integer dactab[128] = { 16, 0, 0, 3, 0, 5, 14, 7, 0, 9, 14, 11, 14, 13, 30, 14, 0, 9,
        2, 7, 4, 7, 7, 23, 9, 25, 10, 9, 12, 9, 14, 7, 0, 5, 2, 11, 5, 21, 6, 5, 8, 11, 11, 27, 12,
        5, 14, 11, 2, 1, 18, 2, 12, 5, 2, 7, 12, 9, 2, 11, 28, 12, 12, 15, 0, 3, 3, 19, 4, 13, 6,
        3, 8, 13, 10, 3, 13, 29, 14, 13, 4, 1, 10, 3, 20, 4, 4, 7, 10, 9, 26, 10, 4, 13, 10, 15, 8,
        1, 6, 3, 6, 5, 22, 6, 24, 8, 8, 11, 8, 13, 6, 15, 1, 17, 2, 1, 4, 1, 6, 15, 8, 1, 10, 15,
        12, 15, 15, 31 };

    integer i__, j, parity;

    /* parity of the 8 bits (signed divisions as the ELF has them; parity is 0..255) */
    parity = *input & 255;
    parity ^= parity / 16;
    parity ^= parity / 4;
    parity ^= parity / 2;
    parity &= 1;
    i__ = dactab[*input & 127];
    *output = i__ & 15;
    j = i__ & 16;
    if (j != 0) {
        /* no error, or a double error in the parity bit */
        if (parity != 0) {
            ++(*errcnt);
        }
    } else {
        ++(*errcnt);
        if (parity == 0) {
            /* uncorrectable */
            ++(*errcnt);
            *output = -1;
        }
    }
    return 0;
}
