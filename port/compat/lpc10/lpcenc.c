/* libpttclient lpcenc.c (provider): encode one frame, 180 samples to 54 bits. From the reference
 * ELF; see lpc10.h. In the ELF the only caller is PTT_Heartbeat (libpttclient.cpp, 0x3f0370). */
#include "lpc10.h"

/* 0x4755b4, 0x4755b8 */
static integer c__180 = 180;
static integer c__10 = 10;

/* 0x3f1450, 220 bytes */
int lpc10_encode(real *speech, integer *bits, struct lpc10_encoder_state *st)
{
    integer irms, voice[2], pitch, ipitv;
    real rc[10];
    integer irc[10];
    real rms;

    if (speech) {
        --speech;
    }
    if (bits) {
        --bits;
    }

    prepro_(&speech[1], &c__180, st);
    analys_(&speech[1], voice, &pitch, &rms, rc, st);
    encode_(voice, &pitch, &rms, rc, &ipitv, &irms, irc);
    chanwr_(&c__10, &ipitv, &irms, irc, &bits[1], st);
    return 0;
}
