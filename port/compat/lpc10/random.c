/* libpttclient random.c (provider): the decoder's 16-bit additive (lagged Fibonacci) noise
 * generator, state in the decoder record. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f48f0, 220 bytes. The sum wraps to 16 bits (sh); the result is the stored halfword. */
integer random_(struct lpc10_decoder_state *st)
{
    integer ret_val;
    integer *j;
    integer *k;
    shortint *y;

    j = &st->j;
    k = &st->k;
    y = &st->y[0];

    y[*k - 1] += y[*j - 1];
    ret_val = y[*k - 1];
    --(*k);
    if (*k <= 0) {
        *k = 5;
    }
    --(*j);
    if (*j <= 0) {
        *j = 5;
    }
    return ret_val;
}
