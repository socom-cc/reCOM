/* Port compatibility header: declarations the game source takes from the Sony EE
 * eetypes.h. Shared and append-only: add declarations, never rewrite or reorder
 * others' lines. `u_long` is deliberately absent: it was 64-bit on Metrowerks PS2
 * and `long` is 32-bit on the ps2dev GCC target. */
#ifndef SOCOM_COMPAT_EETYPES_H
#define SOCOM_COMPAT_EETYPES_H

/* 128-bit integers (DWARF _word128::u128, MW fund type 0xa510, 16 bytes). */
typedef int long128 __attribute__((mode(TI)));
typedef unsigned int u_long128 __attribute__((mode(TI)));

#endif /* SOCOM_COMPAT_EETYPES_H */
