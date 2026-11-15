/* libpttclient f2clib.c (provider): the f2c run-time helpers the LPC-10 units call. From the
 * reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3eefb0, 252 bytes. In the ELF `u` is a 64-bit unsigned long (the library's compiler has
 * 64-bit long): n is sign-extended into it and shifted with dsrl. n is never negative there
 * (n <= 0 returns early unless x == -1, which negates it), so 32 bits give the same result. */
integer pow_ii(integer *ap, integer *bp)
{
    integer pow, x, n;
    unsigned long long u;

    x = *ap;
    n = *bp;
    if (n <= 0) {
        if (n == 0 || x == 1) {
            return 1;
        }
        if (x != -1) {
            return x == 0 ? 1 / x : 0; /* 1 / 0 traps (break 7) in the ELF as well */
        }
        n = -n;
    }
    u = (unsigned long long)(long long)n;
    for (pow = 1;;) {
        if (u & 1) {
            pow *= x;
        }
        if (u >>= 1) {
            x *= x;
        } else {
            break;
        }
    }
    return pow;
}

/* 0x3ef0b0, 164 bytes: |a| with the sign of b, single precision in the ELF. */
real r_sign(real *a, real *b)
{
    real x;

    x = *a >= 0 ? *a : -*a;
    return *b >= 0 ? x : -x;
}

/* 0x3ef160, 204 bytes: nearest integer, in double precision as the ELF has it (fptodp, dpadd /
 * dpsub with 0.5, floor, sign flip, dptoli). */
integer i_nint(real *x)
{
    return (integer)(*x >= 0 ? floor(*x + .5) : -floor(.5 - *x));
}
