/* libpttclient hp100.c (provider): 100 Hz high-pass filter (two biquad sections), state in the
 * encoder record. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3ef370, 484 bytes. Constants as the ELF's words: 1.859076 (0x3fedf634), .8648249
 * (0x3f5d652a), 1.935715 (0x3ff7c582), .9417004 (0x3f711347), .902428 (0x3f670585). */
int hp100_(real *speech, integer *start, integer *end, struct lpc10_encoder_state *st)
{
    integer i__1;
    integer i__;
    real si, err;
    real z11, z21, z12, z22;

    if (speech) {
        --speech;
    }

    z11 = st->z11;
    z21 = st->z21;
    z12 = st->z12;
    z22 = st->z22;

    i__1 = *end;
    for (i__ = *start; i__ <= i__1; ++i__) {
        si = speech[i__];
        err = si + z11 * 0x1.dbec68p0f /* 1.85907602 */ - z21 * 0x1.baca54p-1f /* .864824891 */;
        si = err - z11 * 2.f + z21;
        z21 = z11;
        z11 = err;
        err = si + z12 * 0x1.ef8b04p0f /* 1.93571496 */ - z22 * 0x1.e2268ep-1f /* .941700399 */;
        si = err - z12 * 2.f + z22;
        z22 = z12;
        z12 = err;
        speech[i__] = si * 0x1.ce0b0ap-1f /* .902427971 */;
    }

    st->z11 = z11;
    st->z21 = z21;
    st->z12 = z12;
    st->z22 = z22;
    return 0;
}
