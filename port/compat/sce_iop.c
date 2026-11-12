/* Functional port lane: Sony sifrpc/sifdev calls mapped onto ps2sdk. Not Sony code;
 * nothing here is evidence for the matching lane.
 *
 *   sceSifInitRpc        -> ps2sdk's own sceSifInitRpc (same name)
 *   sceSifRebootIop      -> SifIopReboot (rom0:UDNL <image>) for a cdrom image, after
 *                           unbinding the cdvd and fileio clients so they rebind to the
 *                           new IOP. Any other image (host0: boot) is read on the EE
 *                           side and passed to SifIopRebootBuffer, because PCSX2's IOP
 *                           has no host0: device while UDNL runs. When the image cannot
 *                           be read at all, the IOP is reset to the BIOS modules
 *                           (SifIopReset("", 0)) and the boot goes on.
 *   sceSifSyncIop        -> SifIopSync
 *   sceSifInitIopHeap    -> SifInitIopHeap
 *   sceSifLoadFileReset  -> SifLoadFileExit (SifLoadModule rebinds on next use)
 *   sceFsReset           -> fioExit (fio rebinds on next use)
 *   sceSifLoadModule     -> SifLoadModule; when the game's module cannot be loaded, the
 *                           BIOS copy of the same Sony module (rom0:) is used; modules of
 *                           the offline subsystems (USB, network, voice) are reported
 *                           unavailable and given a pseudo id so the game's retry loops
 *                           end. The sound modules (SDRDRV, 989SND, 989DSTRM) are not
 *                           offline: 989snd's EE client (snd989.c) needs their RPC
 *                           servers, so a failed load is retried as the game does.
 *   sceOpen/Close/Read/Write/Lseek -> newlib open/close/read/write/lseek (ps2sdk routes
 *                           device paths through fio; SCE flags translated to O_*) */
/* fioExit only: unbinds the fileio RPC client across an IOP reboot. */
#define NEWLIB_PORT_AWARE
#include <stdarg.h>
#include <fcntl.h>
#include <unistd.h>
#include <sifrpc.h>
#include <sifdev.h>
#include <loadfile.h>
#include <iopheap.h>
#include <iopcontrol.h>
#include <iopcontrol_special.h>
#include <malloc.h>
#include <string.h>
#include <ctype.h>
#include <fileio.h>
#include <libcdvd.h>

void socom_port_trace(const char *fmt, ...);

/* Pseudo module ids handed out for offline modules (never a real IOP id). */
#define SOCOM_OFFLINE_MODULE_ID 0x7f000000

static void *reboot_image; /* kept until the next reboot: the IOP reads it after we return */

static void unbind_iop_clients(void)
{
    sceCdInit(SCECdEXIT);
    fioExit();
}

int sceSifRebootIop(const char *imgname)
{
    int r;
    int fd;
    int size;

    socom_port_trace("M4: IOP reboot with %s", imgname);

    if (strncmp(imgname, "cdrom", 5) == 0) {
        unbind_iop_clients();
        r = SifIopReboot(imgname);
        if (!r)
            socom_port_trace("M4: IOP reboot refused (%s)", imgname);
        return r;
    }

    fd = open(imgname, O_RDONLY);
    if (fd < 0) {
        socom_port_trace("M4: IOP image %s unavailable (%d): resetting the IOP to the BIOS modules", imgname, fd);
        unbind_iop_clients();
        return SifIopReset("", 0);
    }

    size = lseek(fd, 0, SEEK_END);
    lseek(fd, 0, SEEK_SET);
    if (reboot_image != NULL)
        free(reboot_image);
    reboot_image = memalign(64, size);
    read(fd, reboot_image, size);
    close(fd);
    unbind_iop_clients();
    r = SifIopRebootBuffer(reboot_image, size);
    socom_port_trace("M4: IOP reboot from EE buffer (%d bytes) -> %d", size, r);
    return r;
}

int sceSifSyncIop(void)
{
    return SifIopSync();
}

int sceSifInitIopHeap(void)
{
    return SifInitIopHeap();
}

void sceSifLoadFileReset(void)
{
    SifLoadFileExit();
}

void sceFsReset(void)
{
    fioExit();
}

/* Module base name, upper case, without directory or ";1": "PADMAN.IRX". */
static void module_base(const char *path, char *out, int outsize)
{
    const char *p = path;
    const char *q;
    int n = 0;

    for (q = path; *q; q++)
        if (*q == '\\' || *q == '/' || *q == ':')
            p = q + 1;
    for (; *p && *p != ';' && n < outsize - 1; p++)
        out[n++] = (char)toupper((unsigned char)*p);
    out[n] = '\0';
}

/* Sony modules the BIOS also carries: the game's EE clients talk to the same RPC. */
static const char *const bios_modules[][2] = {
    {"SIO2MAN.IRX", "rom0:SIO2MAN"},
    {"PADMAN.IRX", "rom0:PADMAN"},
    {"MCMAN.IRX", "rom0:MCMAN"},
    {"MCSERV.IRX", "rom0:MCSERV"},
    {"LIBSD.IRX", "rom0:LIBSD"},
};

/* Offline in the port (user decisions: no online, no voice; no USB keyboard). The game
 * never loads the 989snd debug/error variants; they stay listed. */
static const char *const offline_modules[] = {
    "989ERR.IRX", "989SND_D.IRX", "SNDBGET.IRX",
    "USBD.IRX", "USBKB.IRX", "LGAUD.IRX", "HEADSETO.IRX",
    "DEV9.IRX", "SMAP.IRX", "AN986.IRX", "INET.IRX", "INETCTL.IRX", "INETLOG.IRX", "PPP.IRX",
    "PPPOE.IRX", "NETCNF.IRX", "NETCNFIF.IRX", "IFNETCNF.IRX", "EZNETCNF.IRX", "EZNETCTL.IRX",
    "IFCONFIG.IRX", "LIBNETB.IRX", "MSIFRPC.IRX", "PTTCLNT.IRX", "PTTSRVR.IRX", "SETINIT.IRX",
    "IOPPROF.IRX",
};

int sceSifLoadModule(const char *filename, int args, const char *argp)
{
    char base[64];
    unsigned int i;
    int id = SifLoadModule(filename, args, argp);

    if (id >= 0) {
        socom_port_trace("M4: load module %s -> %d", filename, id);
        return id;
    }

    module_base(filename, base, sizeof(base));

    for (i = 0; i < sizeof(bios_modules) / sizeof(bios_modules[0]); i++) {
        if (strcmp(base, bios_modules[i][0]) == 0) {
            int bios = SifLoadModule(bios_modules[i][1], 0, NULL);
            socom_port_trace("M4: load module %s failed (%d); BIOS %s -> %d", filename, id, bios_modules[i][1], bios);
            if (bios >= 0)
                return bios;
            break;
        }
    }

    for (i = 0; i < sizeof(offline_modules) / sizeof(offline_modules[0]); i++) {
        if (strcmp(base, offline_modules[i]) == 0) {
            socom_port_trace("M4: module %s unavailable (%d): offline in the port, continuing without it", filename, id);
            return SOCOM_OFFLINE_MODULE_ID + (int)i;
        }
    }

    socom_port_trace("M4: load module %s failed (%d)", filename, id);
    return id;
}

int sceOpen(const char *filename, int flag, ...)
{
    int oflag;
    int fd;

    switch (flag & SCE_RDWR) {
    case SCE_WRONLY: oflag = O_WRONLY; break;
    case SCE_RDWR: oflag = O_RDWR; break;
    default: oflag = O_RDONLY; break;
    }
    if (flag & SCE_APPEND)
        oflag |= O_APPEND;
    if (flag & SCE_CREAT)
        oflag |= O_CREAT;
    if (flag & SCE_TRUNC)
        oflag |= O_TRUNC;
    if (flag & SCE_EXCL)
        oflag |= O_EXCL;
    fd = open(filename, oflag, 0666);
    if (fd < 0)
        socom_port_trace("FILE: sceOpen(%s, 0x%x) failed (%d): game data not reachable", filename, flag, fd);
    return fd;
}

int sceClose(int fd)
{
    return close(fd);
}

int sceRead(int fd, void *buf, int nbyte)
{
    return read(fd, buf, nbyte);
}

int sceWrite(int fd, const void *buf, int nbyte)
{
    return write(fd, buf, nbyte);
}

int sceLseek(int fd, int offset, int whence)
{
    return lseek(fd, offset, whence);
}

/* Movie player (src/gamez/zMPEG/strfile.cpp, audiodec.cpp): port reads are blocking, so a
 * read is never still executing; IOP heap and EE->IOP DMA map onto ps2sdk directly
 * (sceSifSetDma / sceSifDmaStat come from ps2sdk itself). */

int sceIoctl(int fd, int req, void *arg)
{
    (void)fd;
    if (req == SCE_FS_EXECUTING && arg != NULL)
        *(int *)arg = 0;
    return 0;
}

void *sceSifAllocIopHeap(unsigned int size)
{
    return SifAllocIopHeap(size);
}

int sceSifFreeIopHeap(void *addr)
{
    return SifFreeIopHeap(addr);
}

