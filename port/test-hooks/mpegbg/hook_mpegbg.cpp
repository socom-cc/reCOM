/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-mpegbg, the menus' MPEG background (CGameMenu::LoadFromDesign /
 * TickMPEG / Halt / Restart over CMPEG). Wraps scePadRead and drives the menus from the open dialog's
 * name, queueing menu-stack switches as the anims' UI commands do:
 *  - boot as the game does: dlgIntroScreen, dlgIntroCinematic (sony448.pss), dlgIntroZipperCinematic
 *    (Zipper02.pss), dlgMenu;
 *  - dlgMenu -> dlgPBMenu (BACKGROUND MPEG menuloop.pss; on the first visit its no-memory-card pop-up is closed with CROSS)
 *    for SOCOM_HOOK_LOOP reads (default 130, under the menu's 10 s attract timeout: the 4 s stand-in movie loops twice) -> dlgMenu
 *    (an image background) -> dlgPBMenu again -> dlgMISSIONSELECTION (radar.pss) -> dlgMenu ->
 *    CROSS on NEW GAME: dlgAlaskaCinematic (0100.pss, the game's own) for 150 reads, CROSS skips it
 *    -> dlgAlaska_mission3 (the briefing), where the hook stops.
 * The demo disc has neither menuloop.pss nor radar.pss (the retail looping backgrounds): strFileOpen
 * is wrapped to open SOCOM_HOOK_LOOP_MOVIE (default the 4 s Zipper logo) for menuloop.pss and
 * SOCOM_HOOK_RADAR_MOVIE (default the 4 s Sony title) for radar.pss, so those menus show a movie.
 * Traced (HOOK:): each dialog with the heap (in use, largest free block), each CMPEG::Run / Loop /
 * End with the heap, every 30th picture with the frame time, the menu's movie flags every 30 reads. */
#include <string>
#define protected public
#define private public
#include "gamez/zGame/zgame.h"
#include "gamez/zUI/zui.h"
#include "gamez/zMPEG/zmpeg.h"
#include "gamez/zVideo/zvid.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <malloc.h>
#include <eeregs.h>
#include "hook_clock.h"

#ifndef SOCOM_HOOK_LOOP
#define SOCOM_HOOK_LOOP 130
#endif
#ifndef SOCOM_HOOK_LOOP_MOVIE
#define SOCOM_HOOK_LOOP_MOVIE "run/movies/common/Zipper02.pss"
#endif
#ifndef SOCOM_HOOK_RADAR_MOVIE
#define SOCOM_HOOK_RADAR_MOVIE "run/movies/common/sony448.pss"
#endif

CGameMenu *UiGetCurMenu();
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);
extern "C" unsigned char __real__Z11strFileOpenPKc(const char *name);
extern "C" bool __real__ZN5CMPEG3RunEPKcbb(const char *name, bool loop, bool blocking);
extern "C" bool __real__ZN5CMPEG4LoopEv();
extern "C" void __real__ZN5CMPEG3EndEv();
extern "C" int __real__Z7tickPssP7sceMpegP12playPssRsrcsj(sceMpeg *mp, playPssRsrcs *rsrcs, unsigned int fbp);

namespace
{
enum { B_CROSS = 0x0040 };

struct Press
{
    unsigned int at;
    unsigned short bits;
};

Press g_queue[64];
int g_nqueue;
unsigned int g_reads;
char g_dialog[64];
unsigned int g_since;
int g_step;
unsigned int g_pictures;

void queue(unsigned int at, unsigned short bits)
{
    if (g_nqueue < 64)
    {
        g_queue[g_nqueue].at = at;
        g_queue[g_nqueue].bits = bits;
        g_nqueue++;
    }
}

/* the largest block malloc can hand out now (binary search, each probe freed at once) */
unsigned largest_free()
{
    unsigned lo = 0, hi = 32u << 20;

    while (hi - lo > 4096)
    {
        unsigned mid = lo + (hi - lo) / 2;
        void *p = malloc(mid);

        if (p != NULL)
        {
            free(p);
            lo = mid;
        }
        else
        {
            hi = mid;
        }
    }

    return lo;
}

void heap(const char *what)
{
    struct mallinfo mi = mallinfo();
    SOCOM_PORT_TRACE("HOOK: heap %s: in use %u free %u largest free block %u", what, (unsigned)mi.uordblks,
        (unsigned)mi.fordblks, largest_free());
}

void menu_command(int type, const char *arg)
{
    CMenuStack *stack = GetMenuStack();
    stack->m_top++;
    stack->m_cmds[stack->m_top].type = type;
    strcpy(stack->m_cmds[stack->m_top].arg, arg);
    stack->m_count++;
    SOCOM_PORT_TRACE("HOOK: read %u menu command %d %s", g_reads, type, arg);
}

void switch_to(const char *name, int next)
{
    menu_command(5, name);
    g_step = next;
}

/* steps: 0 dlgMenu -> 1 dlgPBMenu -> 2 dlgMenu -> 3 dlgPBMenu -> 4 dlgMISSIONSELECTION -> 5 dlgMenu (NEW GAME)
 * -> 6 dlgAlaskaCinematic -> 7 the briefing (done) */
void watch()
{
    CGameMenu *menu = UiGetCurMenu();

    if (menu == NULL)
        return;

    const char *name = menu->m_ReaderName.c_str();

    if (strcmp(name, g_dialog) != 0)
    {
        snprintf(g_dialog, sizeof(g_dialog), "%s", name);
        g_since = g_reads;
        SOCOM_PORT_TRACE("HOOK: read %u dialog %s (step %d): movie '%s' has %d running %d", g_reads, name, g_step,
            menu->m_MPEGName.c_str(), (int)menu->m_has_mpeg_background, (int)menu->m_movieRunning);
        heap(name);
    }

    unsigned int t = g_reads - g_since;

    if (t % 30 == 15 && menu->m_has_mpeg_background)
        SOCOM_PORT_TRACE("HOOK: read %u %s: movie running %d, frame time %.4f s, %u pictures", g_reads, name,
            (int)menu->m_movieRunning, zVid.frameTime, g_pictures);

    if (strcmp(name, "dlgMenu.rdr") == 0 && t == 15)
        SOCOM_PORT_TRACE("HOOK: read %u dlgMenu (no movie): frame time %.4f s", g_reads, zVid.frameTime);

    if (g_step == 0 && strcmp(name, "dlgMenu.rdr") == 0 && t == 40)
        switch_to("dlgPBMenu.rdr", 1);
    else if (g_step == 1 && strcmp(name, "dlgPBMenu.rdr") == 0 && t == 20)
        queue(g_reads, B_CROSS);
    else if (g_step == 1 && strcmp(name, "dlgPBMenu.rdr") == 0 && t == SOCOM_HOOK_LOOP)
        switch_to("dlgMenu.rdr", 2);
    else if (g_step == 2 && strcmp(name, "dlgMenu.rdr") == 0 && t == 60)
        switch_to("dlgPBMenu.rdr", 3);
    else if (g_step == 3 && strcmp(name, "dlgPBMenu.rdr") == 0 && t == 120)
        switch_to("dlgMISSIONSELECTION.rdr", 4);
    else if (g_step == 4 && strcmp(name, "dlgMISSIONSELECTION.rdr") == 0 && t == 150)
        switch_to("dlgMenu.rdr", 5);
    else if (g_step == 5 && strcmp(name, "dlgMenu.rdr") == 0 && t == 60)
    {
        queue(g_reads, B_CROSS);
        g_step = 6;
    }
    else if (g_step == 6 && strcmp(name, "dlgAlaskaCinematic.rdr") == 0 && t == 150)
    {
        SOCOM_PORT_TRACE("HOOK: read %u dlgAlaskaCinematic: CROSS (skip)", g_reads);
        queue(g_reads, B_CROSS);
    }
    else if (g_step == 6 && strcmp(name, "dlgAlaska_mission3.rdr") == 0 && t == 60)
    {
        SOCOM_PORT_TRACE("HOOK: read %u briefing: done", g_reads);
        heap("briefing");
        g_step = 7;
    }
}

unsigned short pressed_now()
{
    unsigned short bits = 0;

    for (int i = 0; i < g_nqueue; i++)
    {
        if (g_reads >= g_queue[i].at && g_reads < g_queue[i].at + 3)
            bits |= g_queue[i].bits;
    }

    return bits;
}
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port == 0)
    {
        static unsigned int hook_clock1;
        for (unsigned int hook_n = hook_step(&hook_clock1); hook_n > 0; hook_n--)
        {
            g_reads++;
            watch();
            unsigned short bits = pressed_now();

            if (bits != 0)
            {
                unsigned short held = (unsigned short)(~((rdata[2] << 8) | rdata[3]));
                held |= bits;
                rdata[2] = (unsigned char)~(held >> 8);
                rdata[3] = (unsigned char)~held;
            }
        }
    }

    return r;
}

/* the retail looping backgrounds are not on the demo disc: a stand-in movie for them */
extern "C" unsigned char __wrap__Z11strFileOpenPKc(const char *name)
{
    const char *open = name;

    if (name != NULL && strcasecmp(name, "run/movies/common/menuloop.pss") == 0)
        open = SOCOM_HOOK_LOOP_MOVIE;
    else if (name != NULL && strcasecmp(name, "run/movies/common/radar.pss") == 0)
        open = SOCOM_HOOK_RADAR_MOVIE;

    unsigned char ok = __real__Z11strFileOpenPKc(open);
    SOCOM_PORT_TRACE("HOOK: read %u strFileOpen '%s'%s%s -> %d", g_reads, name ? name : "(null)",
        open != name ? " as " : "", open != name ? open : "", (int)ok);
    return ok;
}

extern "C" bool __wrap__ZN5CMPEG3RunEPKcbb(const char *name, bool loop, bool blocking)
{
    heap("before CMPEG::Run");
    g_pictures = 0;
#ifdef SOCOM_HOOK_BLOCKTEST
    blocking = true; /* diag: the whole movie in one call (playPss), outside the menu's frame loop */
#endif
    bool ok = __real__ZN5CMPEG3RunEPKcbb(name, loop, blocking);
    SOCOM_PORT_TRACE("HOOK: read %u CMPEG::Run '%s' -> %d", g_reads, name ? name : "(null)", (int)ok);
    heap("after CMPEG::Run");
    return ok;
}

extern "C" bool __wrap__ZN5CMPEG4LoopEv()
{
    SOCOM_PORT_TRACE("HOOK: read %u CMPEG::Loop after %u pictures (the movie starts again)", g_reads, g_pictures);
    g_pictures = 0;
    return __real__ZN5CMPEG4LoopEv();
}

extern "C" void __wrap__ZN5CMPEG3EndEv()
{
    SOCOM_PORT_TRACE("HOOK: read %u CMPEG::End after %u pictures", g_reads, g_pictures);
    __real__ZN5CMPEG3EndEv();
    heap("after CMPEG::End");
}

#ifdef SOCOM_HOOK_DIAG
#include <kernel.h>
extern void *_gp;
/* -DSOCOM_HOOK_DIAG: entry / exit of the movie's per-frame calls, the first SOCOM_HOOK_DIAG of each */
extern "C" void __real__ZN5CMPEG8IdleTickEv();
extern "C" int __real_sceMpegGetPicture(sceMpeg *mp, void *rgb32, int mbcount);
extern "C" int __real__Z11strFileReadPvi(void *buf, int size);
extern "C" void __real__Z11zSysFifoEndv();
extern "C" void __real__Z9loadImagePj(unsigned int *tags);
extern "C" int __real_sceMpegDemuxPss(sceMpeg *mp, unsigned char *pss, int size);
extern "C" int __real__Z17audioDecSendToIOPP8AudioDec(AudioDec *dec);
static int g_diag[7];
#define DIAG(i, ...) do { if (g_diag[i] < SOCOM_HOOK_DIAG) SOCOM_PORT_TRACE(__VA_ARGS__); } while (0)

extern "C" int __wrap_sceMpegDemuxPss(sceMpeg *mp, unsigned char *pss, int size)
{
    int r = __real_sceMpegDemuxPss(mp, pss, size);
    DIAG(5, "HOOK: diag DemuxPss %d -> %d", size, r);
    g_diag[5]++;
    return r;
}

extern "C" int __wrap__Z17audioDecSendToIOPP8AudioDec(AudioDec *dec)
{
    int r = __real__Z17audioDecSendToIOPP8AudioDec(dec);
    DIAG(6, "HOOK: diag audioDecSendToIOP -> %d (state %d, ring %d of %d, sent %d, IOP pos %d)", r, dec->state,
        dec->count, dec->size, dec->totalBytesSent, dec->iopLastPos);
    g_diag[6]++;
    return r;
}

extern "C" void __wrap__ZN5CMPEG8IdleTickEv()
{
    DIAG(0, "HOOK: diag IdleTick in (T0 %u)", (unsigned)*T0_COUNT);
    __real__ZN5CMPEG8IdleTickEv();
    DIAG(0, "HOOK: diag IdleTick out (T0 %u)", (unsigned)*T0_COUNT);
    g_diag[0]++;
}

/* a watchdog thread woken from the V-blank interrupt: when a GetPicture has not returned for about
 * 1 s it traces the IPU / DMAC registers and the main thread's state (once) */
static volatile int g_in_picture;
static volatile unsigned g_vblanks, g_picture_since;
static int g_dog_tid, g_main_tid;

static volatile unsigned g_epc[16];
static volatile int g_nepc;

static int dog_vblank(int)
{
    g_vblanks++;
    if (g_in_picture && g_vblanks - g_picture_since > 30 && g_nepc < 16)
    {
        unsigned epc;
        __asm__ volatile("mfc0 %0, $14" : "=r"(epc));
        g_epc[g_nepc++] = epc;
    }
    if ((g_vblanks & 15) == 0 && g_dog_tid > 0)
        iWakeupThread(g_dog_tid);
    return 0;
}

#define R32(a) (*(volatile unsigned int *)(a))
static void dog_main(void *)
{
    int told = 0;
    for (;;)
    {
        SleepThread();
        if (g_in_picture && g_vblanks - g_picture_since > 60 && !told)
        {
            ee_thread_status_t st;
            ReferThreadStatus(g_main_tid, &st);
            SOCOM_PORT_TRACE("HOOK: dog: GetPicture stuck: main thread status %d wait type %d; D3 chcr %08x madr %08x qwc %x; "
                "D4 chcr %08x madr %08x qwc %x; IPU ctrl %08x bp %08x; D_STAT %08x D_CTRL %08x D_PCR %08x ENABLER %08x "
                "INTC_MASK %08x", st.status, st.waitType, R32(0x1000b000), R32(0x1000b010), R32(0x1000b020),
                R32(0x1000b400), R32(0x1000b410), R32(0x1000b420), R32(0x10002010), R32(0x10002020), R32(0x1000e010),
                R32(0x1000e000), R32(0x1000e020), R32(0x1000f520), R32(0x1000f010));
            SOCOM_PORT_TRACE("HOOK: dog: EPC %08x %08x %08x %08x %08x %08x %08x %08x %08x %08x %08x %08x", g_epc[0], g_epc[1], g_epc[2], g_epc[3], g_epc[4], g_epc[5], g_epc[6], g_epc[7], g_epc[8], g_epc[9], g_epc[10], g_epc[11]);
            told = 1;
        }
    }
}

static void dog_start()
{
    static unsigned char stack[16384] __attribute__((aligned(16)));
    ee_thread_t t;
    memset(&t, 0, sizeof(t));
    t.func = (void *)dog_main;
    t.stack = stack;
    t.stack_size = sizeof(stack);
    t.gp_reg = &_gp;
    t.initial_priority = 1;
    g_main_tid = GetThreadId();
    g_dog_tid = CreateThread(&t);
    StartThread(g_dog_tid, NULL);
    AddIntcHandler(INTC_VBLANK_S, dog_vblank, 0);
    EnableIntc(INTC_VBLANK_S);
    SOCOM_PORT_TRACE("HOOK: dog thread %d (main %d)", g_dog_tid, g_main_tid);
}

extern "C" int __wrap_sceMpegGetPicture(sceMpeg *mp, void *rgb32, int mbcount)
{
    if (g_dog_tid == 0)
        dog_start();
    DIAG(1, "HOOK: diag GetPicture in");
    g_picture_since = g_vblanks;
    g_in_picture = 1;
    int r = __real_sceMpegGetPicture(mp, rgb32, mbcount);
    g_in_picture = 0;
    DIAG(1, "HOOK: diag GetPicture out %d", r);
    g_diag[1]++;
    return r;
}

extern "C" int __wrap__Z11strFileReadPvi(void *buf, int size)
{
    int r = __real__Z11strFileReadPvi(buf, size);
    DIAG(2, "HOOK: diag strFileRead %d -> %d", size, r);
    g_diag[2]++;
    return r;
}

extern "C" void __wrap__Z11zSysFifoEndv()
{
    DIAG(3, "HOOK: diag zSysFifoEnd in");
    __real__Z11zSysFifoEndv();
    DIAG(3, "HOOK: diag zSysFifoEnd out");
    g_diag[3]++;
}

extern "C" void __wrap__Z9loadImagePj(unsigned int *tags)
{
    DIAG(4, "HOOK: diag loadImage in %p", tags);
    __real__Z9loadImagePj(tags);
    DIAG(4, "HOOK: diag loadImage out");
    g_diag[4]++;
}
#endif

extern "C" int __wrap__Z7tickPssP7sceMpegP12playPssRsrcsj(sceMpeg *mp, playPssRsrcs *rsrcs, unsigned int fbp)
{
#ifdef SOCOM_HOOK_DIAG
    if (g_pictures < SOCOM_HOOK_DIAG)
        SOCOM_PORT_TRACE("HOOK: diag tickPss in (picture %u)", g_pictures + 1);
#endif
    int r = __real__Z7tickPssP7sceMpegP12playPssRsrcsj(mp, rsrcs, fbp);
    g_pictures++;

    if (g_pictures % 30 == 1)
        SOCOM_PORT_TRACE("HOOK: read %u picture %u (decoder %d, %dx%d) into page %u, frame time %.4f s", g_reads,
            g_pictures, mp->frameCount, mp->width, mp->height, fbp >> 5, zVid.frameTime);

    return r;
}
