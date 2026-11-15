/* libpttclient energy.c (provider): RMS energy of a buffer. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3eeec0, 236 bytes. The square root is single precision (sqrtf) in the ELF. */
int energy_(integer *len, real *speech, real *rms)
{
    integer i__1;
    integer i__;

    --speech;

    *rms = 0.f;
    i__1 = *len;
    for (i__ = 1; i__ <= i__1; ++i__) {
        *rms += speech[i__] * speech[i__];
    }
    *rms = sqrtf(*rms / *len);
    return 0;
}
