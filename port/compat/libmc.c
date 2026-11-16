/* Functional port lane: the Sony libmc calls the game makes (zUtil/util_memcard.cpp, CMemCard
 * and CMemCardIO), mapped onto ps2sdk's libmc, which has the same calls under mc* names and
 * the same argument order. Not Sony code; nothing here is evidence for the matching lane.
 * docs/port/notes/memcard.md has the whole story.
 *
 * The IOP side is the disc's MCMAN.IRX / MCSERV.IRX (zsys_init.cpp loads them at boot; sce_iop.c
 * falls back to the BIOS's rom0:MCMAN / rom0:MCSERV). The game's own libmc (sceMcInit 0x171070,
 * sceMcGetInfo 0x171be8, mceGetInfoApdx 0x171b90) speaks the newer MCSERV protocol: INIT 0xfe,
 * GET_INFO 1 with the format / free / type request words at +12 / +16 / +20 and the answers at
 * +0 / +4 / +144 of a 192-byte block the IOP writes back. The pinned ps2sdk libmc picks that
 * protocol itself (mcInit ignores its argument; it is the "XMC" one there) when the server's
 * INIT answers, and then reads the same words: the card's own answers reach the game unchanged.
 * The result codes (sceMcSync's *result) come from the disc's Sony MCSERV, so they are Sony's.
 *
 * Status: the info reply is right. Earlier runs read "type 2, free 0, format 0" from a card that
 * PCSX2 itself logged as "8 MB, UNFORMATTED": that was the true answer, not a layer defect.
 * What the layer changes against plain ps2sdk (each found by comparing with the ELF's libmc):
 *  - registration results: ps2sdk answers "another call still registered" with that call's
 *    number (> 0); Sony's PollSema answer is -200. No bound client: -100 (as Sony).
 *  - sceMcChdir: Sony's end function (mceStorePwd 0x171f38) skips a NULL curDir, ps2sdk's
 *    (mcStoreDir) copies to it; the game passes NULL (CMemCard::chdir), so the layer passes its
 *    own buffer. A NULL or empty name is refused with -210 as Sony does.
 *  - sceMcGetInfo: the type and format words are always asked for (into the layer's own words
 *    when the game passes NULL) so the layer knows the card's last answer (sceMcFormat below);
 *    the free word only when the game asks (counting free clusters reads the card's FAT).
 *  - sceMcFormat forwards only for the memory-card test hook (see there).
 *
 * Shown in the emulator (port/test-hooks/memcard, the dedicated test card): an unformatted card
 * reads as unformatted (result -2, type 2, format 0, as PCSX2 logs it), the game's own
 * FormatMemCard formats it (1.5 s; 7995 KB free after), its SaveConfig / LoadConfig write and read
 * the options save (BASCUS-97859SOCOM/BASCUS-97859SOCOM) and its icon files, and a second boot
 * loads the saved values. The game's save path needed fixes outside this file (zReader, zArchive,
 * CSTable, sce_iop.c disc reads: docs/port/notes/memcard.md).
 *
 * The card layer is ON (socom_port_memcard = 1): the game's card calls reach whatever card is in
 * the emulator's slot. The demo's reachable screens make none (its card animations are only on
 * screens the demo does not reach); test boots run with empty slots unless they name the
 * dedicated test card (port/tools/dev/pcsx2-boot.ps1 -MemCard). An empty slot answers each info
 * call in about 5 ms (one IOP probe). */
#include <libmc.h>
#include <string.h>

void socom_port_trace(const char *fmt, ...);

extern int _iop_reboot_count; /* ps2sdk: counts IOP reboots (a reboot drops the MCSERV binding) */

/* 1 (normal builds): the game's card calls reach the card. 0: every call answers "no card"
 * (-100); a test may switch it off before the game's first CMemCard::Init. */
int socom_port_memcard = 1;

/* Formatting. Off in every build: sceMcFormat refuses (CMemCard::Format 0x3072c0 then reports
 * failure). Only port/test-hooks/memcard/hook_memcard.cpp sets it, for the dedicated test card the
 * user allowed to be formatted. Even then a card is formatted only when the layer's own last info
 * reply for that port and slot said "PS2 card, not formatted": a card that reads as formatted is
 * never formatted. */
int socom_port_memcard_format = 0;

static int mc_bound;         /* mcInit succeeded */
static int mc_reboot_count;  /* _iop_reboot_count when it did */

/* What was registered last (for the bookkeeping at sceMcSync). */
enum { PEND_NONE, PEND_INFO, PEND_FORMAT, PEND_OTHER };
static int pend_kind;
static int pend_port, pend_slot;
static int *pend_type, *pend_free, *pend_format;
static const char *pend_name; /* PEND_OTHER: the call, for the failure trace */
static int pend_arg;
static int own_type, own_format;
static unsigned int pend_start;

/* The last info reply per port: known = the reply was complete (a PS2 card answered). */
static struct {
    int known, slot, type, format, free_known, free, result;
    int traced, traced_type, traced_format, traced_result;
    unsigned int polls, cycles, max_cycles;
} last[2];

static char own_pwd[1024]; /* sceMcChdir's current directory when the game passes none */

static unsigned int cycles_now(void)
{
    unsigned int c;
    __asm__ volatile("mfc0 %0, $9" : "=r"(c)); /* COP0 Count: the EE clock, 294.912 MHz */
    return c;
}

/* A ps2sdk registration answer in Sony's terms: 0 registered, < 0 refused. */
static int registered(int r, int kind)
{
    if (r == 0) {
        pend_kind = kind;
        return 0;
    }
    pend_kind = PEND_NONE;
    if (r > 0)
        return -200; /* another call still registered (Sony: the PollSema answer) */
    return r;
}

int sceMcInit(void)
{
    int r;

    if (!socom_port_memcard) {
        socom_port_trace("MC: sceMcInit: card layer off (socom_port_memcard = 0): no card");
        return -1;
    }
    if (mc_bound && mc_reboot_count == _iop_reboot_count)
        return 0;
    mc_bound = 0;
    r = mcInit(MC_TYPE_MC); /* the pinned ps2sdk ignores the type: it tries the newer protocol first */
    if (r < 0) {
        int r2 = mcInit(MC_TYPE_MC);
        socom_port_trace("MC: mcInit -> %d, again -> %d", r, r2);
        r = r2;
    }
    if (r >= 0) {
        int cmd, res = 0;
        /* ps2sdk answers mcGetEntSpace with -1 at once on the old protocol: a cheap way to see
         * which one it bound (it reads the card's root directory once) */
        int probe = mcGetEntSpace(0, 0, "/");
        if (probe == 0)
            mcSync(MC_WAIT, &cmd, &res);
        mc_bound = 1;
        mc_reboot_count = _iop_reboot_count;
        memset(last, 0, sizeof(last));
        socom_port_trace("MC: mcInit -> %d: bound, %s protocol (the game's libmc speaks the newer one)", r,
                         probe == 0 ? "newer (GET_INFO 1)" : "old (GET_INFO 0x78)");
    } else {
        socom_port_trace("MC: mcInit -> %d: no card server, every card call answers no card", r);
    }
    return r < 0 ? r : 0;
}

/* The game calls the card functions after its own Init only; a call before a bound client
 * would wait for ever in ps2sdk: answer as Sony's libmc does without a client (-100). */
#define MC_READY() do { if (!mc_bound) return -100; } while (0)

int sceMcGetInfo(int port, int slot, int *type, int *free, int *format)
{
    MC_READY();
    pend_port = port & 1;
    pend_slot = slot;
    pend_type = type != NULL ? type : &own_type;
    pend_free = free;
    pend_format = format != NULL ? format : &own_format;
    last[pend_port].known = 0;
    pend_start = cycles_now();
    return registered(mcGetInfo(port, slot, pend_type, free, pend_format), PEND_INFO);
}

int sceMcOpen(int port, int slot, const char *name, int mode)
{
    MC_READY();
    pend_name = "open";
    pend_arg = mode;
    return registered(mcOpen(port, slot, name, mode), PEND_OTHER);
}

int sceMcClose(int fd)
{
    MC_READY();
    pend_name = "close";
    pend_arg = fd;
    return registered(mcClose(fd), PEND_OTHER);
}

int sceMcSeek(int fd, int offset, int origin)
{
    MC_READY();
    pend_name = "seek";
    pend_arg = offset;
    return registered(mcSeek(fd, offset, origin), PEND_OTHER);
}

int sceMcRead(int fd, void *buf, int size)
{
    MC_READY();
    pend_name = "read";
    pend_arg = size;
    return registered(mcRead(fd, buf, size), PEND_OTHER);
}

int sceMcWrite(int fd, const void *buf, int size)
{
    MC_READY();
    pend_name = "write";
    pend_arg = size;
    return registered(mcWrite(fd, buf, size), PEND_OTHER);
}

int sceMcFlush(int fd)
{
    MC_READY();
    pend_name = "flush";
    pend_arg = fd;
    return registered(mcFlush(fd), PEND_OTHER);
}

int sceMcMkdir(int port, int slot, const char *name)
{
    MC_READY();
    pend_name = "mkdir";
    pend_arg = 0;
    return registered(mcMkDir(port, slot, name), PEND_OTHER);
}

int sceMcChdir(int port, int slot, const char *newDir, char *curDir)
{
    MC_READY();
    if (newDir == NULL || newDir[0] == '\0')
        return -210; /* Sony's sceMcChdir (0x172034) */
    pend_name = "chdir";
    pend_arg = 0;
    return registered(mcChdir(port, slot, newDir, curDir != NULL ? curDir : own_pwd), PEND_OTHER);
}

int sceMcGetDir(int port, int slot, const char *name, unsigned int mode, int maxent, sceMcTblGetDir *table)
{
    MC_READY();
    pend_name = "getdir";
    pend_arg = maxent;
    return registered(mcGetDir(port, slot, name, mode, maxent, table), PEND_OTHER);
}

int sceMcDelete(int port, int slot, const char *name)
{
    MC_READY();
    pend_name = "delete";
    pend_arg = 0;
    return registered(mcDelete(port, slot, name), PEND_OTHER);
}

int sceMcFormat(int port, int slot)
{
    int p = port & 1;

    MC_READY();
    if (!socom_port_memcard_format) {
        socom_port_trace("MC: sceMcFormat(%d, %d) refused: formatting is off in the port (only the memory-card test hook allows it)", port, slot);
        return -1;
    }
    if (!last[p].known || last[p].slot != slot || last[p].type != sceMcTypePS2 || last[p].format != 0) {
        socom_port_trace("MC: sceMcFormat(%d, %d) refused: the last info reply (known %d, type %d, format %d) is not an unformatted PS2 card",
                         port, slot, last[p].known, last[p].type, last[p].format);
        return -1;
    }
    socom_port_trace("MC: sceMcFormat(%d, %d): last info reply PS2 card, unformatted (result %d): formatting", port, slot, last[p].result);
    last[p].known = 0;
    pend_port = p;
    pend_slot = slot;
    pend_start = cycles_now();
    return registered(mcFormat(port, slot), PEND_FORMAT);
}

static void info_done(int result)
{
    unsigned int took = cycles_now() - pend_start;
    int p = pend_port;

    last[p].slot = pend_slot;
    last[p].type = *pend_type;
    last[p].format = *pend_format;
    last[p].result = result;
    if (pend_free != NULL) {
        last[p].free_known = 1;
        last[p].free = *pend_free;
    }
    /* a complete answer: the card is there and answered (Sony: 0 same card, -1 new formatted
     * card, -2 new unformatted card) */
    last[p].known = (result == 0 || result == -1 || result == -2);
    last[p].polls++;
    last[p].cycles += took;
    if (took > last[p].max_cycles)
        last[p].max_cycles = took;
    if (!last[p].traced || last[p].traced_type != last[p].type || last[p].traced_format != last[p].format ||
        (last[p].traced_result < -2) != (result < -2) || result == -1 || result == -2) {
        socom_port_trace("MC: info port %d slot %d: result %d, type %d (%s), format %d (%s), free %s%d; %u us (poll %u)", p, pend_slot,
                         result, last[p].type,
                         last[p].type == sceMcTypePS2 ? "PS2 card" : last[p].type == sceMcTypeNoCard ? "no card" : "other",
                         last[p].format, last[p].format ? "formatted" : "not formatted",
                         pend_free != NULL ? "" : "(not asked) ", pend_free != NULL ? *pend_free : last[p].free,
                         took / 295, last[p].polls);
        last[p].traced = 1;
        last[p].traced_type = last[p].type;
        last[p].traced_format = last[p].format;
        last[p].traced_result = result;
    }
}

/* Port only (test hooks and the memory-card note): polls, total and longest info round trip in
 * microseconds for a port. */
void socom_port_memcard_poll_stats(int port, unsigned int *polls, unsigned int *total_us, unsigned int *max_us)
{
    int p = port & 1;

    *polls = last[p].polls;
    *total_us = last[p].cycles / 295;
    *max_us = last[p].max_cycles / 295;
}

int sceMcSync(int mode, int *cmd, int *result)
{
    int c = 0, r = 0, ret;

    if (!mc_bound) {
        if (result != NULL)
            *result = -10; /* port: nothing was registered; the game never syncs then */
        return -1;
    }
    ret = mcSync(mode != 0 ? MC_NOWAIT : MC_WAIT, &c, &r);
    if (cmd != NULL)
        *cmd = c;
    if (ret == 1) {
        if (result != NULL)
            *result = r;
        if (pend_kind == PEND_INFO) {
            info_done(r);
        } else if (pend_kind == PEND_OTHER && (r < 0 ? strcmp(pend_name, "getdir") != 0 : strcmp(pend_name, "write") == 0 && (r != pend_arg || pend_arg <= 0))) {
            /* failures (a directory search that finds nothing is an answer, not a failure),
             * short and empty writes */
            socom_port_trace("MC: %s (%d) -> result %d", pend_name, pend_arg, r);
        } else if (pend_kind == PEND_FORMAT) {
            socom_port_trace("MC: sceMcFormat(%d, %d) -> result %d, %u ms", pend_port, pend_slot, r,
                             (cycles_now() - pend_start) / 294912);
        }
        pend_kind = PEND_NONE;
    }
    return ret;
}
