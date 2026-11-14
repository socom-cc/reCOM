/* Port compatibility header: the Sony EE libmc.h (memory card). ps2sdk ships a libmc.h of
 * the same name (mc* calls, the sceMc* types and constants); this header chains to it and
 * declares the Sony sceMc* calls the game makes, implemented in port/compat/libmc.c on
 * ps2sdk's libmc. Prototypes follow the game's call sites (zUtil/util_memcard.cpp).
 * Shared and append-only. */
#ifndef SOCOM_COMPAT_LIBMC_H
#define SOCOM_COMPAT_LIBMC_H

#include_next <libmc.h>

#ifdef __cplusplus
extern "C" {
#endif

int sceMcInit(void);
int sceMcGetInfo(int port, int slot, int *type, int *free, int *format);
int sceMcOpen(int port, int slot, const char *name, int mode);
int sceMcClose(int fd);
int sceMcSeek(int fd, int offset, int origin);
int sceMcRead(int fd, void *buf, int size);
int sceMcWrite(int fd, const void *buf, int size);
int sceMcFlush(int fd);
int sceMcMkdir(int port, int slot, const char *name);
int sceMcChdir(int port, int slot, const char *newDir, char *curDir);
int sceMcGetDir(int port, int slot, const char *name, unsigned int mode, int maxent, sceMcTblGetDir *table);
int sceMcDelete(int port, int slot, const char *name);
int sceMcFormat(int port, int slot);
int sceMcSync(int mode, int *cmd, int *result);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_LIBMC_H */
