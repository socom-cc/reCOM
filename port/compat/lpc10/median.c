/* libpttclient median.c (provider): median of three. From the reference ELF; see lpc10.h. */
#include "lpc10.h"

/* 0x3f21b0, 260 bytes */
integer median_(integer *d1, integer *d2, integer *d3)
{
    integer ret_val;

    ret_val = *d2;
    if (*d2 > *d1 && *d2 > *d3) {
        ret_val = *d1;
        if (*d3 > *d1) {
            ret_val = *d3;
        }
    } else if (*d2 < *d1 && *d2 < *d3) {
        ret_val = *d1;
        if (*d3 < *d1) {
            ret_val = *d3;
        }
    }
    return ret_val;
}
