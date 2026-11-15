/* libpttclient pitsyn.c (provider): synthesis-side interpolation of pitch, voicing, RMS and the
 * reflection coefficients (as log-area ratios) per pitch period across the frame, with the
 * voiced / unvoiced transition cases. State in the decoder record. From the reference ELF; see
 * lpc10.h. */
#include "lpc10.h"

/* 0x3f2b00, 3292 bytes. log and exp are single precision (logf / expf) in the ELF; the float to
 * integer conversions are truncating (fptosi). */
int pitsyn_(integer *order, integer *voice, integer *pitch, real *rms, real *rc, integer *lframe,
            integer *ivuv, integer *ipiti, real *rmsi, real *rci, integer *nout, real *ratio,
            struct lpc10_decoder_state *st)
{
    integer rci_dim1 = 0, rci_offset, i__1, i__2;
    real r__1;
    real alrn, alro, yarc[10], prop;
    integer i__, j, vflag, jused, lsamp;
    integer *jsamp;
    real slope;
    integer *ipito;
    real uvpit;
    integer ip, nl, ivoice;
    integer *ivoico;
    integer istart;
    real *rmso;
    real xxy;
    real *rco;
    logical *first;

    if (rc) {
        --rc;
    }
    if (rci) {
        rci_dim1 = *order;
        rci_offset = rci_dim1 + 1;
        rci -= rci_offset;
    }
    if (voice) {
        --voice;
    }
    if (ivuv) {
        --ivuv;
    }
    if (ipiti) {
        --ipiti;
    }
    if (rmsi) {
        --rmsi;
    }

    ivoico = &st->ivoico;
    ipito = &st->ipito;
    rmso = &st->rmso;
    rco = &st->rco[0];
    jsamp = &st->jsamp;
    first = &st->first_pitsyn;

    if (*rms < 1.f) {
        *rms = 1.f;
    }
    if (*rmso < 1.f) {
        *rmso = 1.f;
    }
    uvpit = 0.f;
    *ratio = *rms / (*rmso + 8.f);
    if (*first) {
        lsamp = 0;
        ivoice = voice[2];
        if (ivoice == 0) {
            *pitch = *lframe / 4;
        }
        *nout = *lframe / *pitch;
        *jsamp = *lframe - *nout * *pitch;
        i__1 = *nout;
        for (i__ = 1; i__ <= i__1; ++i__) {
            i__2 = *order;
            for (j = 1; j <= i__2; ++j) {
                rci[j + i__ * rci_dim1] = rc[j];
            }
            ivuv[i__] = ivoice;
            ipiti[i__] = *pitch;
            rmsi[i__] = *rms;
        }
        *first = FALSE_;
    } else {
        vflag = 0;
        lsamp = *lframe + *jsamp;
        slope = (*pitch - *ipito) / (real)lsamp;
        *nout = 0;
        jused = 0;
        istart = 1;
        if (voice[1] == *ivoico && voice[2] == voice[1]) {
            if (voice[2] == 0) {
                /* SSUV: 0, 0, 0 */
                *pitch = *lframe / 4;
                *ipito = *pitch;
                if (*ratio > 8.f) {
                    *rmso = *rms;
                }
            }
            /* SSVC: 1, 1, 1 */
            slope = (*pitch - *ipito) / (real)lsamp;
            ivoice = voice[2];
        } else {
            if (*ivoico != 1) {
                if (*ivoico == voice[1]) {
                    /* UV2VC2: 0, 0, 1 */
                    nl = lsamp - *lframe / 4;
                } else {
                    /* UV2VC1: 0, 1, 1 */
                    nl = lsamp - *lframe * 3 / 4;
                }
                ipiti[1] = nl / 2;
                ipiti[2] = nl - ipiti[1];
                ivuv[1] = 0;
                ivuv[2] = 0;
                rmsi[1] = *rmso;
                rmsi[2] = *rmso;
                i__1 = *order;
                for (i__ = 1; i__ <= i__1; ++i__) {
                    rci[i__ + rci_dim1] = rco[i__ - 1];
                    rci[i__ + (rci_dim1 << 1)] = rco[i__ - 1];
                    rco[i__ - 1] = rc[i__];
                }
                slope = 0.f;
                *nout = 2;
                *ipito = *pitch;
                jused = nl;
                istart = nl + 1;
                ivoice = 1;
            } else {
                if (*ivoico != voice[1]) {
                    /* VC2UV1: 1, 0, 0 */
                    lsamp = *lframe / 4 + *jsamp;
                } else {
                    /* VC2UV2: 1, 1, 0 */
                    lsamp = *lframe * 3 / 4 + *jsamp;
                }
                i__1 = *order;
                for (i__ = 1; i__ <= i__1; ++i__) {
                    yarc[i__ - 1] = rc[i__];
                    rc[i__] = rco[i__ - 1];
                }
                ivoice = 1;
                slope = 0.f;
                vflag = 1;
            }
        }
L100:
        /* one pitch period per epoch that fits, parameters interpolated at its middle */
        i__1 = lsamp;
        for (i__ = istart; i__ <= i__1; ++i__) {
            r__1 = *ipito + slope * i__;
            ip = r__1 + .5f;
            if (uvpit != 0.f) {
                ip = uvpit;
            }
            if (ip <= i__ - jused) {
                ++(*nout);
                ipiti[*nout] = ip;
                *pitch = ip;
                ivuv[*nout] = ivoice;
                jused += ip;
                prop = (jused - ip / 2) / (real)lsamp;
                i__2 = *order;
                for (j = 1; j <= i__2; ++j) {
                    alro = logf((rco[j - 1] + 1) / (1 - rco[j - 1]));
                    alrn = logf((rc[j] + 1) / (1 - rc[j]));
                    xxy = alro + prop * (alrn - alro);
                    xxy = expf(xxy);
                    rci[j + *nout * rci_dim1] = (xxy - 1) / (xxy + 1);
                }
                rmsi[*nout] = logf(*rmso) + prop * (logf(*rms) - logf(*rmso));
                rmsi[*nout] = expf(rmsi[*nout]);
            }
        }
        if (vflag != 1) {
            goto L200;
        }
        /* voiced to unvoiced: the unvoiced rest of the frame */
        vflag = 0;
        istart = jused + 1;
        lsamp = *lframe + *jsamp;
        slope = 0.f;
        ivoice = 0;
        uvpit = (real)((lsamp - istart) / 2);
        if (uvpit > 90.f) {
            uvpit /= 2;
        }
        *rmso = *rms;
        i__1 = *order;
        for (i__ = 1; i__ <= i__1; ++i__) {
            rc[i__] = yarc[i__ - 1];
            rco[i__ - 1] = yarc[i__ - 1];
        }
        goto L100;
L200:
        *jsamp = lsamp - jused;
    }
    /* this frame's parameters become the old ones */
    if (*nout != 0) {
        *ivoico = voice[2];
        *ipito = *pitch;
        *rmso = *rms;
        i__1 = *order;
        for (i__ = 1; i__ <= i__1; ++i__) {
            rco[i__ - 1] = rc[i__];
        }
    }
    return 0;
}
