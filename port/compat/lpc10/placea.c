/* libpttclient placea.c (provider): place the analysis and energy windows, pitch-synchronously
 * in sustained voiced speech. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f37e0, 2576 bytes */
int placea_(integer *ipitch, integer *voibuf, integer *obound, integer *af, integer *vwin,
            integer *awin, integer *ewin, integer *lframe, integer *maxwin)
{
    real r__1;
    logical allv, winv;
    integer i__, j, k, l, hrange;
    logical ephase;
    integer lrange;

    ewin -= 3;
    awin -= 3;
    vwin -= 3;
    --voibuf;

    lrange = (*af - 2) * *lframe + 1;
    hrange = *af * *lframe;
    /* case 1 (sustained voiced: the five latest decisions voiced) and case 2 (voiced transition
     * without onsets) are placed phase-synchronously; case 3 (unvoiced or onsets) takes the
     * voicing window */
    allv = voibuf[((*af - 2) << 1) + 2] == 1;
    allv = allv && voibuf[((*af - 1) << 1) + 1] == 1;
    allv = allv && voibuf[((*af - 1) << 1) + 2] == 1;
    allv = allv && voibuf[(*af << 1) + 1] == 1;
    allv = allv && voibuf[(*af << 1) + 2] == 1;
    winv = voibuf[(*af << 1) + 1] == 1 || voibuf[(*af << 1) + 2] == 1;
    if (allv || (winv && *obound == 0)) {
        /* APHASE: the lowest pitch-synchronous start in range */
        i__ = (lrange + *ipitch - 1 - awin[((*af - 1) << 1) + 1]) / *ipitch;
        i__ *= *ipitch;
        i__ += awin[((*af - 1) << 1) + 1];
        l = *maxwin;
        /* where a centred window would start; take the closest pitch multiple */
        k = (vwin[(*af << 1) + 1] + vwin[(*af << 1) + 2] + 1 - l) / 2;
        r__1 = (real)(k - i__) / *ipitch;
        awin[(*af << 1) + 1] = i__ + i_nint(&r__1) * *ipitch;
        awin[(*af << 1) + 2] = awin[(*af << 1) + 1] + l - 1;
        /* keep clear of an onset bounding the voicing window on the right ... */
        if (*obound >= 2 && awin[(*af << 1) + 2] > vwin[(*af << 1) + 2]) {
            awin[(*af << 1) + 1] -= *ipitch;
            awin[(*af << 1) + 2] -= *ipitch;
        }
        /* ... and on the left */
        if ((*obound == 1 || *obound == 3) && awin[(*af << 1) + 1] < vwin[(*af << 1) + 1]) {
            awin[(*af << 1) + 1] += *ipitch;
            awin[(*af << 1) + 2] += *ipitch;
        }
        /* back inside HRANGE .. LRANGE by whole pitch periods */
        while (awin[(*af << 1) + 2] > hrange) {
            awin[(*af << 1) + 1] -= *ipitch;
            awin[(*af << 1) + 2] -= *ipitch;
        }
        while (awin[(*af << 1) + 1] < lrange) {
            awin[(*af << 1) + 1] += *ipitch;
            awin[(*af << 1) + 2] += *ipitch;
        }
        ephase = TRUE_;
    } else {
        awin[(*af << 1) + 1] = vwin[(*af << 1) + 1];
        awin[(*af << 1) + 2] = vwin[(*af << 1) + 2];
        ephase = FALSE_;
    }
    /* the energy window: a whole number of pitch periods in the analysis window, as close to
     * the onsets as possible when not phase-synchronous */
    j = (awin[(*af << 1) + 2] - awin[(*af << 1) + 1] + 1) / *ipitch * *ipitch;
    if (j == 0 || !winv) {
        ewin[(*af << 1) + 1] = vwin[(*af << 1) + 1];
        ewin[(*af << 1) + 2] = vwin[(*af << 1) + 2];
    } else if (!ephase && *obound == 2) {
        ewin[(*af << 1) + 1] = awin[(*af << 1) + 2] - j + 1;
        ewin[(*af << 1) + 2] = awin[(*af << 1) + 2];
    } else {
        ewin[(*af << 1) + 1] = awin[(*af << 1) + 1];
        ewin[(*af << 1) + 2] = awin[(*af << 1) + 1] + j - 1;
    }
    return 0;
}
