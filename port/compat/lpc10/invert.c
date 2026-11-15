/* libpttclient invert.c (provider): Cholesky solution of the covariance equations for the
 * reflection coefficients. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3ef560, 1212 bytes. 1e-10 is 0x2edbe6ff, .999 is 0x3f7fbe77. */
int invert_(integer *order, real *phi, real *psi, real *rc)
{
    integer phi_dim1, phi_offset, i__1, i__2, i__3;
    real r__1, r__2;
    real save;
    integer i__, j, k;
    real v[100]; /* was [10][10] */

    --rc;
    --psi;
    phi_dim1 = *order;
    phi_offset = phi_dim1 + 1;
    phi -= phi_offset;

    i__1 = *order;
    for (j = 1; j <= i__1; ++j) {
        i__2 = *order;
        for (i__ = j; i__ <= i__2; ++i__) {
            v[i__ + j * 10 - 11] = phi[i__ + j * phi_dim1];
        }
        i__2 = j - 1;
        for (k = 1; k <= i__2; ++k) {
            save = v[j + k * 10 - 11] * v[k + k * 10 - 11];
            i__3 = *order;
            for (i__ = j; i__ <= i__3; ++i__) {
                v[i__ + j * 10 - 11] -= v[i__ + k * 10 - 11] * save;
            }
        }
        /* intermediate results, similar to the RCs */
        if ((r__1 = v[j + j * 10 - 11], abs(r__1)) < 0x1.b7cdfep-34f /* 1e-10 */) {
            goto L100;
        }
        rc[j] = psi[j];
        i__2 = j - 1;
        for (k = 1; k <= i__2; ++k) {
            rc[j] -= rc[k] * v[j + k * 10 - 11];
        }
        v[j + j * 10 - 11] = 1.f / v[j + j * 10 - 11];
        rc[j] *= v[j + j * 10 - 11];
        r__2 = rc[j];
        r__1 = min(r__2, 0x1.ff7ceep-1f /* .999000013 */);
        rc[j] = max(r__1, -0x1.ff7ceep-1f /* .999000013 */);
    }
    return 0;
    /* zero the remaining RCs once the matrix is singular */
L100:
    i__1 = *order;
    for (i__ = j; i__ <= i__1; ++i__) {
        rc[i__] = 0.f;
    }
    return 0;
}
