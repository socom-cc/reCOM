/* libpttclient mload.c (provider): load the covariance matrix and vector of the analysis window.
 * From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f22c0, 940 bytes */
int mload_(integer *order, integer *awins, integer *awinf, real *speech, real *phi, real *psi)
{
    integer phi_dim1, phi_offset, i__1, i__2;
    integer c__, i__, r__, start;

    --psi;
    phi_dim1 = *order;
    phi_offset = phi_dim1 + 1;
    phi -= phi_offset;
    --speech;

    /* first column of PHI and the last element of PSI by direct summation */
    start = *awins + *order;
    i__1 = *order;
    for (r__ = 1; r__ <= i__1; ++r__) {
        phi[r__ + phi_dim1] = 0.f;
        i__2 = *awinf;
        for (i__ = start; i__ <= i__2; ++i__) {
            phi[r__ + phi_dim1] += speech[i__ - 1] * speech[i__ - r__];
        }
    }
    psi[*order] = 0.f;
    i__1 = *awinf;
    for (i__ = start; i__ <= i__1; ++i__) {
        psi[*order] += speech[i__] * speech[i__ - *order];
    }
    /* the rest of PHI by end correction */
    i__1 = *order;
    for (r__ = 2; r__ <= i__1; ++r__) {
        i__2 = r__;
        for (c__ = 2; c__ <= i__2; ++c__) {
            phi[r__ + c__ * phi_dim1] = phi[r__ - 1 + (c__ - 1) * phi_dim1]
                - speech[*awinf + 1 - r__] * speech[*awinf + 1 - c__]
                + speech[start - r__] * speech[start - c__];
        }
    }
    /* the rest of PSI */
    i__1 = *order - 1;
    for (c__ = 1; c__ <= i__1; ++c__) {
        psi[c__] = phi[c__ + 1 + phi_dim1] - speech[start - 1] * speech[start - 1 - c__]
            + speech[*awinf] * speech[*awinf - c__];
    }
    return 0;
}
