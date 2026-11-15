/* libpttclient decode.c (provider): decode the quantised parameters of a frame, with the error
 * correction of the protected bits (Hamming 8,4) and median smoothing over three frames. State
 * in the decoder record. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

static integer c__2 = 2; /* 0x4755a8 */

/* 0x3ecda0, 4060 bytes; tables at 0x43c670..0x43cbc4 (equal to the ELF's data). ethrs,
 * ethrs1, ethrs2 and ethrs3 are .sbss words set on the first call, each under its own init$N
 * guard, in the ELF; plain initialised statics here (never written). The three-frame histories
 * hold the newest frame at index 0 (dpit[0], drms[0], drc[3 * (i - 1)]) and are shifted towards
 * index 2. The float to integer conversions are truncating (fptosi in the ELF). */
int decode_(integer *ipitv, integer *irms, integer *irc, integer *voice, integer *pitch, real *rms,
            real *rc, struct lpc10_decoder_state *st)
{
    static integer ethrs = 2048;
    static integer ethrs1 = 128;
    static integer ethrs2 = 1024;
    static integer ethrs3 = 2048;
    static integer ivtab[32] = { 24960, 24960, 24960, 24960, 25480, 25480, 25483, 25480, 16640,
        1560, 1560, 1560, 16640, 1816, 1563, 1560, 24960, 24960, 24859, 24856, 26001, 25881, 25915,
        25913, 1560, 1560, 7800, 3640, 1561, 1561, 3643, 3641 };
    static real corth[32] = { 32767.f, 10.f, 5.f, 0.f, 32767.f, 8.f, 4.f, 0.f, 32.f, 0x1.99999ap2f /* 6.4000001 */,
        0x1.99999ap1f /* 3.20000005 */, 0.f, 32.f, 0x1.99999ap2f /* 6.4000001 */, 0x1.99999ap1f /* 3.20000005 */, 0.f, 32.f, 0x1.666666p3f /* 11.1999998 */, 0x1.99999ap2f /* 6.4000001 */, 0.f,
        32.f, 0x1.666666p3f /* 11.1999998 */, 0x1.99999ap2f /* 6.4000001 */, 0.f, 16.f, 0x1.666666p2f /* 5.5999999 */, 0x1.99999ap1f /* 3.20000005 */, 0.f, 16.f, 0x1.666666p2f /* 5.5999999 */,
        0x1.99999ap1f /* 3.20000005 */, 0.f };
    static integer detau[128] = { 0, 0, 0, 3, 0, 3, 3, 31, 0, 3, 3, 21, 3, 3, 29, 30, 0, 3, 3, 20,
        3, 25, 27, 26, 3, 23, 58, 22, 3, 24, 28, 3, 0, 3, 3, 3, 3, 39, 33, 32, 3, 37, 35, 36, 3,
        38, 34, 3, 3, 42, 46, 44, 50, 40, 48, 3, 54, 3, 56, 3, 52, 3, 3, 1, 0, 3, 3, 108, 3, 78,
        100, 104, 3, 84, 92, 88, 156, 80, 96, 3, 3, 74, 70, 72, 66, 76, 68, 3, 62, 3, 60, 3, 64, 3,
        3, 1, 3, 116, 132, 112, 148, 152, 3, 3, 140, 3, 136, 3, 144, 3, 3, 1, 124, 120, 128, 3, 3,
        3, 3, 1, 3, 3, 3, 1, 3, 1, 1, 1 };
    static integer rmst[64] = { 1024, 936, 856, 784, 718, 656, 600, 550, 502, 460, 420, 384, 352,
        328, 294, 270, 246, 226, 206, 188, 172, 158, 144, 132, 120, 110, 102, 92, 84, 78, 70, 64,
        60, 54, 50, 46, 42, 38, 34, 32, 30, 26, 24, 22, 20, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9,
        8, 7, 6, 5, 4, 3, 2, 1, 0 };
    static integer detab7[32] = { 4, 11, 18, 25, 32, 39, 46, 53, 60, 66, 72, 77, 82, 87, 92, 96,
        101, 104, 108, 111, 114, 115, 117, 119, 121, 122, 123, 124, 125, 126, 127, 127 };
    static real descl[8] = { 0x1.63fe5cp-1f /* .695299983 */, .625f, 0x1.27fcbap-1f /* .578100026 */, 0x1.180346p-1f /* .546899974 */, 0x1.0ff972p-1f /* .531199992 */,
        0x1.1404eap-1f /* .539099991 */, 0x1.e00d1cp-2f /* .468800008 */, 0x1.87fcbap-2f /* .382800013 */ };
    static integer deadd[8] = { 1152, -2816, -1536, -3584, -1280, -2432, 768, -1920 };
    static integer qb[8] = { 511, 511, 1023, 1023, 1023, 1023, 2047, 4095 };
    static integer nbit[10] = { 8, 8, 5, 5, 4, 4, 4, 4, 3, 2 };
    static integer zrc[10] = { 0, 0, 0, 0, 0, 3, 0, 2, 0, 0 };
    static integer bit[5] = { 2, 4, 8, 16, 32 };

    integer i__1, i__2;
    integer ishift, errcnt, lsb;
    integer i__, i1, i2, i4;
    integer ixcor, iout, ipit;
    integer icorf, index, ivoic;
    integer *iptold, *first, *ivp2h, *iovoic, *iavgp, *erate, *drc, *dpit, *drms;

    iptold = &st->iptold;
    first = &st->first;
    ivp2h = &st->ivp2h;
    iovoic = &st->iovoic;
    iavgp = &st->iavgp;
    erate = &st->erate;
    drc = &st->drc[0];
    dpit = &st->dpit[0];
    drms = &st->drms[0];

    if (irc) {
        --irc;
    }
    if (voice) {
        --voice;
    }
    if (rc) {
        --rc;
    }

    /* without error correction: pitch and voicing, then decode */
    i4 = detau[*ipitv];
    if (!contrl_.corrp) {
        voice[1] = 1;
        voice[2] = 1;
        if (*ipitv <= 1) {
            voice[1] = 0;
        }
        if (*ipitv == 0 || *ipitv == 2) {
            voice[2] = 0;
        }
        *pitch = i4;
        if (*pitch <= 4) {
            *pitch = *iptold;
        }
        if (voice[1] == 1 && voice[2] == 1) {
            *iptold = *pitch;
        }
        if (voice[1] != voice[2]) {
            *pitch = *iptold;
        }
        goto L900;
    }
    /* error-corrected pitch and voicing */
    if (i4 > 4) {
        dpit[0] = i4;
        ivoic = 2;
        *iavgp = (*iavgp * 15 + i4 + 8) / 16;
    } else {
        ivoic = i4;
        dpit[0] = *iavgp;
    }
    drms[0] = *irms;
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        drc[i__ * 3 - 3] = irc[i__];
    }
    /* the IVTAB entry for this voicing history; the alternate table when the error rate is
     * high */
    index = (*ivp2h << 4) + (*iovoic << 2) + ivoic + 1;
    i1 = ivtab[index - 1];
    ipit = i1 & 3;
    icorf = i1 / 8;
    if (*erate < ethrs) {
        icorf /= 64;
    }
    /* error rate class: 4 high .. 1 low */
    ixcor = 4;
    if (*erate < ethrs3) {
        ixcor = 3;
    }
    if (*erate < ethrs2) {
        ixcor = 2;
    }
    if (*erate < ethrs1) {
        ixcor = 1;
    }
    /* voicing from bits 0 and 1 of the entry */
    voice[1] = icorf / 2 & 1;
    voice[2] = icorf & 1;
    /* nothing to decode yet on the first frame */
    if (*first) {
        *first = FALSE_;
        *pitch = i4;
        if (*pitch <= 4) {
            *pitch = *iptold;
        }
        goto L500;
    }
    /* bit 4: correct RMS and RC(1) - RC(4) with the Hamming (8,4) code (transition or unvoiced
     * frame); an uncorrectable word keeps the previous frame's value */
    if ((icorf & bit[3]) != 0) {
        errcnt = 0;
        lsb = drms[1] & 1;
        index = (drc[22] << 4) + drms[1] / 2;
        ham84_(&index, &iout, &errcnt);
        drms[1] = drms[2];
        if (iout >= 0) {
            drms[1] = (iout << 1) + lsb;
        }
        for (i__ = 1; i__ <= 4; ++i__) {
            if (i__ == 1) {
                i1 = ((drc[25] & 7) << 1) + (drc[28] & 1);
            } else {
                i1 = drc[(9 - i__) * 3 - 2] & 15;
            }
            i2 = drc[(5 - i__) * 3 - 2] & 31;
            lsb = i2 & 1;
            index = (i1 << 4) + i2 / 2;
            ham84_(&index, &iout, &errcnt);
            if (iout >= 0) {
                iout = (iout << 1) + lsb;
                if ((iout & 16) == 16) {
                    iout += -32;
                }
            } else {
                iout = drc[(5 - i__) * 3 - 1];
            }
            drc[(5 - i__) * 3 - 2] = iout;
        }
        /* the running error rate */
        *erate = (integer)(*erate * .96875f + errcnt * 102);
    }
    /* unsmoothed RMS, RCs and pitch of the middle frame */
    *irms = drms[1];
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        irc[i__] = drc[i__ * 3 - 2];
    }
    if (ipit == 1) {
        dpit[1] = dpit[2];
    }
    if (ipit == 3) {
        dpit[1] = dpit[0];
    }
    *pitch = dpit[1];
    /* bit 2: median-smooth RMS and RC(1) - RC(6) */
    if ((icorf & bit[1]) != 0) {
        if ((i__1 = drms[1] - drms[0], (real)abs(i__1)) >= corth[ixcor + 3]
            && (i__2 = drms[1] - drms[2], (real)abs(i__2)) >= corth[ixcor + 3]) {
            *irms = median_(&drms[2], &drms[1], &drms[0]);
        }
        for (i__ = 1; i__ <= 6; ++i__) {
            if ((i__1 = drc[i__ * 3 - 2] - drc[i__ * 3 - 3], (real)abs(i__1))
                    >= corth[ixcor + ((i__ + 2) << 2) - 5]
                && (i__2 = drc[i__ * 3 - 2] - drc[i__ * 3 - 1], (real)abs(i__2))
                    >= corth[ixcor + ((i__ + 2) << 2) - 5]) {
                irc[i__] = median_(&drc[i__ * 3 - 1], &drc[i__ * 3 - 2], &drc[i__ * 3 - 3]);
            }
        }
    }
    /* bit 3: median-smooth the pitch */
    if ((icorf & bit[2]) != 0) {
        if ((i__1 = dpit[1] - dpit[0], (real)abs(i__1)) >= corth[ixcor - 1]
            && (i__2 = dpit[1] - dpit[2], (real)abs(i__2)) >= corth[ixcor - 1]) {
            *pitch = median_(&dpit[2], &dpit[1], &dpit[0]);
        }
    }
L500:
    /* bit 5: RC(5) - RC(10) take the values that decode to zero */
    if ((icorf & bit[4]) != 0) {
        i__1 = contrl_.order;
        for (i__ = 5; i__ <= i__1; ++i__) {
            irc[i__] = zrc[i__ - 1];
        }
    }
    /* one frame of delay */
    *iovoic = ivoic;
    *ivp2h = voice[2];
    dpit[2] = dpit[1];
    dpit[1] = dpit[0];
    drms[2] = drms[1];
    drms[1] = drms[0];
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        drc[i__ * 3 - 1] = drc[i__ * 3 - 2];
        drc[i__ * 3 - 2] = drc[i__ * 3 - 3];
    }
L900:
    /* RMS */
    *irms = rmst[(31 - *irms) * 2];
    /* RC(1) and RC(2) from log-area ratios; the illegal code -16 (a bit error) becomes 0 */
    for (i__ = 1; i__ <= 2; ++i__) {
        i2 = irc[i__];
        i1 = 0;
        if (i2 < 0) {
            i1 = 1;
            i2 = -i2;
            if (i2 > 15) {
                i2 = 0;
            }
        }
        i2 = detab7[i2 * 2];
        if (i1 == 1) {
            i2 = -i2;
        }
        ishift = 15 - nbit[i__ - 1];
        irc[i__] = i2 * pow_ii(&c__2, &ishift);
    }
    /* RC(3) - RC(10) to sign plus 14 bits */
    i__1 = contrl_.order;
    for (i__ = 3; i__ <= i__1; ++i__) {
        i2 = irc[i__];
        ishift = 15 - nbit[i__ - 1];
        i2 *= pow_ii(&c__2, &ishift);
        i2 += qb[i__ - 3];
        irc[i__] = (integer)(i2 * descl[i__ - 3] + deadd[i__ - 3]);
    }
    /* RMS and RCs as reals */
    *rms = (real)*irms;
    i__1 = contrl_.order;
    for (i__ = 1; i__ <= i__1; ++i__) {
        rc[i__] = irc[i__] / 16384.f;
    }
    return 0;
}
