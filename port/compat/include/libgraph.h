/* Port compatibility header: declarations the game source takes from the Sony EE
 * libgraph.h. Shared and append-only: add declarations, never rewrite or reorder
 * others' lines. Layouts come from the game's DWARF; `unsigned long` was 64-bit
 * on Metrowerks PS2, so 64-bit fields are spelled `unsigned long long` here. */
#ifndef SOCOM_COMPAT_LIBGRAPH_H
#define SOCOM_COMPAT_LIBGRAPH_H

/* DWARF sceGsAlpha: class, 8 bytes, bitfields of `unsigned long` (8 bytes on MW). */
typedef struct {
	unsigned long long A:2;
	unsigned long long B:2;
	unsigned long long C:2;
	unsigned long long D:2;
	unsigned long long pad8:24;
	unsigned long long FIX:8;
	unsigned long long pad40:24;
} sceGsAlpha;

#endif /* SOCOM_COMPAT_LIBGRAPH_H */
