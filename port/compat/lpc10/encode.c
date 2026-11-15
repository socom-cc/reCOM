/* libpttclient encode.c (provider): quantise pitch, voicing, RMS and the reflection coefficients
 * (RC1-RC2 as log-area ratios, RC3-RC10 linearly), with the parity protection of unvoiced frames.
 * From the reference ELF; see lpc10.h. */
#include "lpc10.h"

static integer c__2 = 2; /* 0x4755ac */

/* 0x3ee790, 1836 bytes; tables at 0x43cbd0..0x43cf60 (equal to the ELF's data). The float to
 * integer conversions are truncating (fptosi in the ELF). */
int encode_(integer *voice, integer *pitch, real *rms, real *rc, integer *ipitch, integer *irms,
            integer *irc)
{
    static integer enctab[16] = { 0, 7, 11, 12, 13, 10, 6, 1, 14, 9, 5, 2, 3, 4, 8, 15 };
    static integer entau[60] = { 19, 11, 27, 25, 29, 21, 23, 22, 30, 14, 15, 7, 39, 38, 46, 42,
        43, 41, 45, 37, 53, 49, 51, 50, 54, 52, 60, 56, 58, 26, 90, 88, 92, 84, 86, 82, 83, 81, 85,
        69, 77, 73, 75, 74, 78, 70, 71, 67, 99, 97, 113, 112, 114, 98, 106, 104, 108, 100, 101,
        76 };
    static integer enadd[8] = { 1920, -768, 2432, 1280, 3584, 1536, 2816, -1152 };
    static real enscl[8] = { 0x1.4e3bcep-6f /* .0204000007 */, 0x1.119ce0p-6f /* .0166999996 */, 0x1.db22d0p-7f /* .0144999996 */, 0x1.e1b08ap-7f /* .0147000002 */,
        0x1.d49518p-7f /* .0142999999 */, 0x1.ba5e36p-7f /* .0135000004 */, 0x1.99999ap-7f /* .0125000002 */, 0x1.6f0068p-7f /* .0111999996 */ };
    static integer enbits[8] = { 6, 5, 4, 4, 4, 4, 3, 3 };
    static integer entab6[64] = { 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 3,
        3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6, 6, 6, 6, 6, 7, 7, 7, 7, 7, 8, 8, 8,
        8, 9, 9, 9, 10, 10, 11, 11, 12, 13, 14, 15 };
    static integer rmst[64] = { 1024, 936, 856, 784, 718, 656, 600, 550, 502, 460, 420, 384, 352,
        328, 294, 270, 246, 226, 206, 188, 172, 158, 144, 132, 120, 110, 102, 92, 84, 78, 70, 64,
        60, 54, 50, 46, 42, 38, 34, 32, 30, 26, 24, 22, 20, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9,
        8, 7, 6, 5, 4, 3, 2, 1, 0 };

    integer i__1, i__2;
    integer idel, nbit, i__, j, i2, i3, mrk;

    --irc;
    --rc;
    --voice;

    /* scale RMS and the RCs to integers */
    *irms = *rms;
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        irc[i__] = rc[i__] * 32768.f;
    }
    /* pitch and voicing */
    if (voice[1] != 0 && voice[2] != 0) {
        *ipitch = entau[*pitch - 1];
    } else {
        if (contrl_.corrp) {
            *ipitch = 0;
            if (voice[1] != voice[2]) {
                *ipitch = 127;
            }
        } else {
            *ipitch = (voice[1] << 1) + voice[2];
        }
    }
    /* RMS by binary table search */
    j = 32;
    idel = 16;
    *irms = min(*irms, 1023);
    while (idel > 0) {
        if (*irms > rmst[j - 1]) {
            j -= idel;
        }
        if (*irms < rmst[j - 1]) {
            j += idel;
        }
        idel /= 2;
    }
    if (*irms > rmst[j - 1]) {
        --j;
    }
    *irms = 31 - j / 2;
    /* RC(1) and RC(2) as log-area ratios */
    for (i__ = 1; i__ <= 2; ++i__) {
        i2 = irc[i__];
        mrk = 0;
        if (i2 < 0) {
            i2 = -i2;
            mrk = 1;
        }
        i2 /= 512;
        i2 = min(i2, 63);
        i2 = entab6[i2];
        if (mrk != 0) {
            i2 = -i2;
        }
        irc[i__] = i2;
    }
    /* RC(3) - RC(10) linearly: remove the bias, then scale */
    i__1 = contrl_.order;
    for (i__ = 3; i__ <= i__1; ++i__) {
        i2 = irc[i__] / 2;
        i2 = (integer)((i2 + enadd[contrl_.order + 1 - i__ - 1]) * enscl[contrl_.order + 1 - i__ - 1]);
        i__2 = max(i2, -127);
        i2 = min(i__2, 127);
        nbit = enbits[contrl_.order + 1 - i__ - 1];
        i3 = 0;
        if (i2 < 0) {
            i3 = -1;
        }
        i2 /= pow_ii(&c__2, &nbit);
        if (i3 == -1) {
            --i2;
        }
        irc[i__] = i2;
    }
    /* unvoiced frames: 20 parity bits protecting RC(1) - RC(4) and RMS replace RC(5) - RC(10) */
    if (contrl_.corrp) {
        if (*ipitch == 0 || *ipitch == 127) {
            irc[5] = enctab[(irc[1] & 30) / 2];
            irc[6] = enctab[(irc[2] & 30) / 2];
            irc[7] = enctab[(irc[3] & 30) / 2];
            irc[8] = enctab[(*irms & 30) / 2];
            irc[9] = enctab[(irc[4] & 30) / 2] / 2;
            irc[10] = enctab[(irc[4] & 30) / 2] & 1;
        }
    }
    return 0;
}
