/* libpttclient lpfilt.c (provider): 31-tap symmetric FIR low-pass (800 Hz) ahead of the pitch
 * analysis. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f1c70, 1332 bytes. Coefficients as the ELF's words (0xbc1f4178 .. 0x3e804640). */
int lpfilt_(real *inbuf, real *lpbuf, integer *len, integer *nsamp)
{
    integer i__1;
    integer j;
    real t;

    --lpbuf;
    --inbuf;

    i__1 = *len;
    for (j = *len + 1 - *nsamp; j <= i__1; ++j) {
        t = (inbuf[j] + inbuf[j - 30]) * -0x1.3e82f0p-7f /* .00972019881 */;
        t += (inbuf[j - 1] + inbuf[j - 29]) * -0x1.58a75ep-7f /* .0105179986 */;
        t += (inbuf[j - 2] + inbuf[j - 28]) * -0x1.118bcep-7f /* .00834796485 */;
        t += (inbuf[j - 3] + inbuf[j - 27]) * 0x1.3345fap-11f /* .000586077396 */;
        t += (inbuf[j - 4] + inbuf[j - 26]) * 0x1.ace83ep-7f /* .0130892089 */;
        t += (inbuf[j - 5] + inbuf[j - 25]) * 0x1.639e4ep-6f /* .0217052232 */;
        t += (inbuf[j - 6] + inbuf[j - 24]) * 0x1.2dbad4p-6f /* .0184161253 */;
        t += (inbuf[j - 7] + inbuf[j - 23]) * 0x1.6439b2p-12f /* .000339722988 */;
        t += (inbuf[j - 8] + inbuf[j - 22]) * -0x1.ab4a3ap-6f /* .0260797087 */;
        t += (inbuf[j - 9] + inbuf[j - 21]) * -0x1.7532a2p-5f /* .0455563702 */;
        t += (inbuf[j - 10] + inbuf[j - 20]) * -0x1.4a319ap-5f /* .040306855 */;
        t += (inbuf[j - 11] + inbuf[j - 19]) * 0x1.07b54ep-11f /* .000502983516 */;
        t += (inbuf[j - 12] + inbuf[j - 18]) * 0x1.2ab4c2p-4f /* .0729262903 */;
        t += (inbuf[j - 13] + inbuf[j - 17]) * 0x1.41f28ap-3f /* .157200888 */;
        t += (inbuf[j - 14] + inbuf[j - 16]) * 0x1.cc3ea6p-3f /* .224728867 */;
        t += inbuf[j - 15] * 0x1.008c80p-2f /* .250535965 */;
        lpbuf[j] = t;
    }
    return 0;
}
