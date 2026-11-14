/* Functional port lane: the Sony libmc calls the game makes (zUtil/util_memcard.cpp, CMemCard
 * and CMemCardIO), mapped onto ps2sdk's libmc, which has the same calls under mc* names and
 * the same argument order. Not Sony code; nothing here is evidence for the matching lane.
 *
 * The IOP side is the disc's MCMAN.IRX / MCSERV.IRX (RebootIOP loads them on the first boot;
 * sce_iop.c falls back to the BIOS's rom0:MCMAN / rom0:MCSERV). ps2sdk binds MCSERV with
 * mcInit(type): the newer (SDK 2.x) server is MC_TYPE_XMC, the BIOS one MC_TYPE_MC; the
 * newer protocol is tried first.
 *
 * Status (runs sysmc5 / sysmc6, port/test-hooks/memcard): with the disc's MCMAN 2.06 / MCSERV
 * both mcInit types bind and mcGetInfo sees the card (type 2, sync result 0), but the free
 * space and format words come back 0, so CMemCard::IsFormatted says no and the game goes no
 * further (the IOP image also registers an mcman 1.01 before the disc's). Matching the disc
 * server's info reply (or loading the BIOS card modules instead) is the open item.
 *
 * sceMcSync: Sony's waits with its mode 0 (as here: MC_WAIT) and fills *cmd / *result, either
 * of which the game may pass as NULL; ps2sdk's needs both. */
#include <libmc.h>

void socom_port_trace(const char *fmt, ...);

static int mc_type = -1;

/* Off by default: the game then gets "no card" from every call below, as it did before this
 * layer existed. In the emulator the card is the user's own memory-card file; this layer does
 * not read it correctly yet (status note above); and only one emulator can open the file at a
 * time, so with several test runs going the first would see a card and the others none, and
 * their menus would differ. The memory-card test hook (port/test-hooks/memcard) sets this to 1
 * before the game's card Init; nothing in a normal build does. */
int socom_port_memcard = 0;

int sceMcInit(void)
{
    int r;

    if (mc_type >= 0)
        return 0;
    if (!socom_port_memcard) {
        socom_port_trace("MC: sceMcInit: card layer off (socom_port_memcard = 0): no card");
        return -1;
    }
    r = mcInit(MC_TYPE_XMC);
    if (r >= 0) {
        mc_type = MC_TYPE_XMC;
    } else {
        r = mcInit(MC_TYPE_MC);
        if (r >= 0)
            mc_type = MC_TYPE_MC;
    }
    socom_port_trace("MC: mcInit -> %d (type %s)", r, mc_type == MC_TYPE_XMC ? "XMC" : mc_type == MC_TYPE_MC ? "MC" : "none");
    return r;
}

/* The game calls the card functions after its own Init only, but a call before a bound
 * client would wait for ever in ps2sdk: answer "no card" (-1) instead. */
#define MC_READY() do { if (mc_type < 0) return -1; } while (0)

/* ps2sdk's mcGetInfo stores all three answers (when the following mcSync completes); the
 * game passes NULL for those it does not want, so they go to scratch words here. */
static int info_type, info_free, info_format;

int sceMcGetInfo(int port, int slot, int *type, int *free, int *format)
{
    MC_READY();
    return mcGetInfo(port, slot, type != NULL ? type : &info_type, free != NULL ? free : &info_free,
                     format != NULL ? format : &info_format);
}

int sceMcOpen(int port, int slot, const char *name, int mode)
{
    MC_READY();
    return mcOpen(port, slot, name, mode);
}

int sceMcClose(int fd)
{
    MC_READY();
    return mcClose(fd);
}

int sceMcSeek(int fd, int offset, int origin)
{
    MC_READY();
    return mcSeek(fd, offset, origin);
}

int sceMcRead(int fd, void *buf, int size)
{
    MC_READY();
    return mcRead(fd, buf, size);
}

int sceMcWrite(int fd, const void *buf, int size)
{
    MC_READY();
    return mcWrite(fd, buf, size);
}

int sceMcFlush(int fd)
{
    MC_READY();
    return mcFlush(fd);
}

int sceMcMkdir(int port, int slot, const char *name)
{
    MC_READY();
    return mcMkDir(port, slot, name);
}

int sceMcChdir(int port, int slot, const char *newDir, char *curDir)
{
    MC_READY();
    return mcChdir(port, slot, newDir, curDir);
}

int sceMcGetDir(int port, int slot, const char *name, unsigned int mode, int maxent, sceMcTblGetDir *table)
{
    MC_READY();
    return mcGetDir(port, slot, name, mode, maxent, table);
}

int sceMcDelete(int port, int slot, const char *name)
{
    MC_READY();
    return mcDelete(port, slot, name);
}

int sceMcFormat(int port, int slot)
{
    /* Refused on purpose. In the emulator the card is the user's own memory-card file, shared
     * with their other games, and this layer still reads a good card as unformatted (see the
     * status note at the top), so the game's "format?" path would erase it. Returning an error
     * makes CMemCard::Format (0x3072c0) report failure. Do not forward to mcFormat() until
     * sceMcGetInfo's format word is right and the user has agreed to formatting. */
    (void)port;
    (void)slot;
    socom_port_trace("MC: sceMcFormat refused (port layer never formats the user's card)");
    return -1;
}

int sceMcSync(int mode, int *cmd, int *result)
{
    int c, r, ret;

    (void)mode;
    if (mc_type < 0) {
        if (result != NULL)
            *result = -10; /* no card */
        return -1;
    }
    ret = mcSync(MC_WAIT, &c, &r);
    if (cmd != NULL)
        *cmd = c;
    if (result != NULL)
        *result = r;
    return ret;
}
