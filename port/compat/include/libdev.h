/* Port compatibility header: the Sony EE libdev.h (debug font). Implemented in
 * port/compat/libdev.c. Prototypes follow the game's call sites. Shared and append-only. */
#ifndef SOCOM_COMPAT_LIBDEV_H
#define SOCOM_COMPAT_LIBDEV_H

#ifdef __cplusplus
extern "C" {
#endif

/* Builds a GIF DMA packet drawing `str` at (x, y, z) in GS primitive coordinates (x, y
 * 12.4 fixed point) into `packet`; returns the end of the packet. Called by CTTY::Render
 * (zvid_draw.cpp, 0x308f40; the SDK copy is at 0x151bc0 in socom.elf). */
void *sceDevFont(void *packet, int x, int y, int z, char *str, int ctxt);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_LIBDEV_H */
