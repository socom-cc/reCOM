/* libpttclient lpcdec.c (provider): decode one frame, 54 bits to 180 samples. From the reference
 * ELF; see lpc10.h. In the ELF the only caller is PTT_Heartbeat (libpttclient.cpp, 0x3f0370). */
#include "lpc10.h"

static integer c__10 = 10; /* 0x4755b0 */

/* 0x3f1380, 200 bytes */
int lpc10_decode(integer *bits, real *speech, struct lpc10_decoder_state *st)
{
    integer irms, voice[2], pitch, ipitv;
    real rc[10];
    integer irc[10], len;
    real rms;

    if (bits) {
        --bits;
    }
    if (speech) {
        --speech;
    }

    chanrd_(&c__10, &ipitv, &irms, irc, &bits[1]);
    decode_(&ipitv, &irms, irc, voice, &pitch, &rms, rc, st);
    synths_(voice, &pitch, &rms, rc, &speech[1], &len, st);
    return 0;
}
