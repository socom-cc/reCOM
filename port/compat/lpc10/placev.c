/* libpttclient placev.c (provider): place the voicing window from the onsets. From the reference
 * ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f41f0, 1476 bytes. oslen and dvwinh are not read (the ELF never stores a2 or loads the
 * last stack argument). */
int placev_(integer *osbuf, integer *osptr, integer *oslen, integer *obound, integer *vwin,
            integer *af, integer *lframe, integer *minwin, integer *maxwin, integer *dvwinl,
            integer *dvwinh)
{
    integer i__1, i__2;
    logical crit;
    integer i__, q, osptr1, hrange, lrange;

    (void)oslen;
    (void)dvwinh;

    --osbuf;
    vwin -= 3;

    /* the placement range */
    i__1 = vwin[((*af - 1) << 1) + 2] + 1, i__2 = (*af - 2) * *lframe + 1;
    lrange = max(i__1, i__2);
    hrange = *af * *lframe;
    /* OSPTR1: only the onsets up to HRANGE matter */
    for (osptr1 = *osptr - 1; osptr1 >= 1; --osptr1) {
        if (osbuf[osptr1] <= hrange) {
            goto L90;
        }
    }
L90:
    ++osptr1;
    /* case 1: no onset in range */
    if (osptr1 <= 1 || osbuf[osptr1 - 1] < lrange) {
        i__1 = vwin[((*af - 1) << 1) + 2] + 1;
        vwin[(*af << 1) + 1] = max(i__1, *dvwinl);
        vwin[(*af << 1) + 2] = vwin[(*af << 1) + 1] + *maxwin - 1;
        *obound = 0;
    } else {
        /* the first onset in range */
        for (q = osptr1 - 1; q >= 1; --q) {
            if (osbuf[q] < lrange) {
                goto L100;
            }
        }
L100:
        ++q;
        /* critical region exception */
        crit = FALSE_;
        i__1 = osptr1 - 1;
        for (i__ = q + 1; i__ <= i__1; ++i__) {
            if (osbuf[i__] - osbuf[q] >= *minwin) {
                crit = TRUE_;
                goto L105;
            }
        }
L105:
        i__1 = (*af - 1) * *lframe, i__2 = lrange + *minwin - 1;
        if (!crit && osbuf[q] > max(i__1, i__2)) {
            /* case 2: window before the onset */
            vwin[(*af << 1) + 2] = osbuf[q] - 1;
            i__1 = lrange, i__2 = vwin[(*af << 1) + 2] - *maxwin + 1;
            vwin[(*af << 1) + 1] = max(i__1, i__2);
            *obound = 2;
        } else {
            /* case 3: window after the onset, up to the next one */
            vwin[(*af << 1) + 1] = osbuf[q];
L110:
            ++q;
            if (q >= osptr1) {
                goto L120;
            }
            if (osbuf[q] > vwin[(*af << 1) + 1] + *maxwin) {
                goto L120;
            }
            if (osbuf[q] < vwin[(*af << 1) + 1] + *minwin) {
                goto L110;
            }
            vwin[(*af << 1) + 2] = osbuf[q] - 1;
            *obound = 3;
            return 0;
            /* case 4: window after the onset, full length */
L120:
            i__1 = vwin[(*af << 1) + 1] + *maxwin - 1;
            vwin[(*af << 1) + 2] = min(i__1, hrange);
            *obound = 1;
        }
    }
    return 0;
}
