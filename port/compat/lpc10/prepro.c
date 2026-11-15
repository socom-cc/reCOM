/* libpttclient prepro.c (provider): input pre-processing (the 100 Hz high-pass). From the
 * reference ELF; see lpc10.h. */
#include "lpc10.h"

static integer c__1 = 1; /* 0x4755c0 */

/* 0x3f4890, 92 bytes */
int prepro_(real *speech, integer *length, struct lpc10_encoder_state *st)
{
    if (speech) {
        --speech;
    }
    hp100_(&speech[1], &c__1, length, st);
    return 0;
}
