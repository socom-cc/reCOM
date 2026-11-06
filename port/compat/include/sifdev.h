/* Port compatibility header: the Sony EE sifdev.h (IOP file I/O and module/IOP control).
 * Implemented in port/compat/sce_iop.c on ps2sdk fileio, loadfile, iopheap and
 * iopcontrol. Prototypes follow the game's call sites. Shared and append-only: add
 * declarations, never rewrite or reorder others' lines. */
#ifndef SOCOM_COMPAT_SIFDEV_H
#define SOCOM_COMPAT_SIFDEV_H

/* Open flags (same values as the IOP ioman flags ps2sdk fioOpen takes). */
#define SCE_RDONLY 0x0001
#define SCE_WRONLY 0x0002
#define SCE_RDWR 0x0003
#define SCE_APPEND 0x0100
#define SCE_CREAT 0x0200
#define SCE_TRUNC 0x0400
#define SCE_EXCL 0x0800

#define SCE_SEEK_SET 0
#define SCE_SEEK_CUR 1
#define SCE_SEEK_END 2

#ifdef __cplusplus
extern "C" {
#endif

int sceOpen(const char *filename, int flag, ...);
int sceClose(int fd);
int sceRead(int fd, void *buf, int nbyte);
int sceWrite(int fd, const void *buf, int nbyte);
int sceLseek(int fd, int offset, int whence);

int sceSifLoadModule(const char *filename, int args, const char *argp);
int sceSifRebootIop(const char *imgname);
int sceSifSyncIop(void);
int sceSifInitIopHeap(void);
void sceSifLoadFileReset(void);
void sceFsReset(void);

#ifdef __cplusplus
}
#endif

#endif /* SOCOM_COMPAT_SIFDEV_H */
