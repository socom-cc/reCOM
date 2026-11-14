/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-mod-state, the game-state round trips. Wraps scePadRead and
 * drives the pad from what it sees: the top of theGame's state stack and, in the menus, the name of
 * the open dialog (CGameMenu::m_ReaderName), so no read numbers are guessed across loads.
 *  - menus: dlgIntroScreen / dlgMenu / dlgHype: CROSS; the m8 briefing (dlgAlaska_mission3):
 *    DOWN x5 to the deploy button, CROSS. After SOCOM_HOOK_MISSIONS missions the hook stops
 *    pressing and the menus idle (the attract screen comes after ~10 s at dlgMenu).
 *  - cinematic on top: CROSS after 40 reads (the intro movie);
 *  - mission n: the briefing cameras are skipped with X (CROSS every 60 reads while one plays);
 *    SOCOM_HOOK_PLAY_AT reads after the last camera: odd n pause START, row 1 (ABORT), CROSS;
 *    even n the player's real fatal fall (HandleFallingDamage 300, as port/test-hooks/death);
 *  - debrief (exit state on top): TRIANGLE (back to the briefing) after 300 reads, again every 150.
 * Every state and dialog change is traced with the heap: newlib's mallinfo (arena, in use, free,
 * top chunk) and the program break. -DSOCOM_HOOK_MALLOC also wraps malloc / memalign / realloc /
 * calloc and traces every failed request with the heap figures. */
#include <map>
#include <string>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zGame/zgame.h"
#include "Apps/FTS/state/state.h"
#include "Apps/FTS/hud/hud.h"
#include <string.h>
#include <stdio.h>
#include <malloc.h>
#include <unistd.h>
#include <stdint.h>

#ifndef SOCOM_HOOK_PLAY_AT
#define SOCOM_HOOK_PLAY_AT 300
#endif
#ifndef SOCOM_HOOK_MISSIONS
#define SOCOM_HOOK_MISSIONS 4
#endif

extern COurGame theGame;
void hook_state_heap_extra(const char *what);
void hook_state_arm();
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

namespace
{
enum { B_UP = 0x1000, B_DOWN = 0x4000, B_START = 0x0800, B_CROSS = 0x0040, B_TRIANGLE = 0x0010 };

struct Press
{
    unsigned int at;
    unsigned short bits;
};

Press g_queue[256];
int g_nqueue;
unsigned int g_reads;
const void *g_top;
unsigned int g_top_since;
std::string g_dialog;
int g_mission;
bool g_new_mission;
unsigned int g_last_cam;       /* read of the last frame a mission camera played */
unsigned int g_mission_since;
bool g_acted;                  /* this mission's pause / death is done */
int g_pause_target = -1;
unsigned int g_pause_from;
unsigned int g_pause_next;
int g_exit_pressed;
int g_returns;

void queue(unsigned int at, unsigned short bits)
{
    if (g_nqueue < 256)
    {
        g_queue[g_nqueue].at = at;
        g_queue[g_nqueue].bits = bits;
        g_nqueue++;
    }
}

const char *name_of(const void *s)
{
    if (s == &theGame.m_menuState) return "menu";
    if (s == &theGame.m_loadState) return "load";
    if (s == &theGame.m_coreState) return "core";
    if (s == &theGame.m_exitState) return "exit";
    if (s == &theGame.m_cinematicSubState) return "cinematic";
    return s != NULL ? "other" : "none";
}

const void *top_state()
{
    const void *top = NULL;

    for (unsigned int i = 0; i < 16; i++)
        if (theGame.m_Stack[i] != NULL)
            top = theGame.m_Stack[i];

    return top;
}

void heap(const char *what)
{
    struct mallinfo mi = mallinfo();
    SOCOM_PORT_TRACE("HOOK: heap %s: arena %u in use %u free %u top %u brk %p", what, (unsigned)mi.arena,
        (unsigned)mi.uordblks, (unsigned)mi.fordblks, (unsigned)mi.keepcost, sbrk(0));
    hook_state_heap_extra(what);
}

bool camera_playing()
{
    return theHUD != NULL && theHUD->m_missioncams.IsPlaying() != 0;
}

void on_dialog(const std::string &name)
{
    if (g_mission >= SOCOM_HOOK_MISSIONS)
    {
        SOCOM_PORT_TRACE("HOOK: read %u dialog %s: idle (done with %d missions)", g_reads, name.c_str(), g_mission);
        return;
    }

    if (name == "dlgIntroScreen.rdr" || name == "dlgMenu.rdr" || name == "dlgHype.rdr")
    {
        queue(g_reads + 90, B_CROSS);
        SOCOM_PORT_TRACE("HOOK: read %u dialog %s: CROSS", g_reads, name.c_str());
    }
    else if (name == "dlgAlaska_mission3.rdr")
    {
        for (int i = 0; i < 5; i++)
            queue(g_reads + 150 + 10 * i, B_DOWN);

        queue(g_reads + 210, B_CROSS);
        SOCOM_PORT_TRACE("HOOK: read %u dialog %s: DOWN x5, CROSS (deploy)", g_reads, name.c_str());
    }
    else
    {
        SOCOM_PORT_TRACE("HOOK: read %u dialog %s", g_reads, name.c_str());
    }
}

void watch()
{
    static bool armed = false;

    if (!armed)
    {
        hook_state_arm(); /* from the first pad read: boot's resident blocks are tagged too */
        armed = true;
    }

    const void *top = top_state();

    if (top != g_top)
    {
        SOCOM_PORT_TRACE("HOOK: read %u state %s -> %s (index %u, mission %d)", g_reads, name_of(g_top), name_of(top),
            (unsigned)theGame.m_CurrentState, g_mission);

        if (top == &theGame.m_menuState && g_mission > 0)
        {
            g_returns++;
            char what[48];
            snprintf(what, sizeof(what), "return %d to the menus", g_returns);
            heap(what);
        }

        g_top = top;
        g_top_since = g_reads;
        g_dialog.clear();

        if (top == &theGame.m_cinematicSubState)
            queue(g_reads + 40, B_CROSS);
        else if (top == &theGame.m_exitState)
            g_exit_pressed = 0;
    }

    if (top == &theGame.m_menuState && theGame.m_menuState.m_menu != NULL)
    {
        const char *name = theGame.m_menuState.m_menu->m_ReaderName.c_str();

        if (g_dialog != name)
        {
            g_dialog = name;
            heap(name);
            on_dialog(g_dialog);
        }
    }

    if (top == &theGame.m_exitState && g_reads >= g_top_since + 300 && (g_reads - g_top_since - 300) % 150 == 0 && g_exit_pressed < 6)
    {
        SOCOM_PORT_TRACE("HOOK: read %u debrief: TRIANGLE (mission %d)", g_reads, g_mission);
        queue(g_reads + 1, B_TRIANGLE);
        g_exit_pressed++;
    }

    if (g_new_mission)
    {
        g_new_mission = false;
        g_mission++;
        g_mission_since = g_reads;
        g_last_cam = 0;
        g_acted = false;
        SOCOM_PORT_TRACE("HOOK: read %u mission %d starts (player %p)", g_reads, g_mission, (void *)ftsGetPlayer());
        heap("mission start");
    }

    if (top == &theGame.m_coreState && g_mission > 0 && !g_acted)
    {
        if (camera_playing())
        {
            if (g_last_cam == 0 || g_reads >= g_last_cam + 60)
            {
                SOCOM_PORT_TRACE("HOOK: read %u X skips mission camera %s", g_reads,
                    theHUD->m_missioncams.m_currentcam != NULL ? theHUD->m_missioncams.m_currentcam->m_identifier : "-");
                queue(g_reads + 1, B_CROSS);
                g_last_cam = g_reads;
            }
        }
        else if (g_reads >= (g_last_cam != 0 ? g_last_cam : g_mission_since + 400) + SOCOM_HOOK_PLAY_AT)
        {
            g_acted = true;

            if (g_mission % 2 == 1)
            {
                SOCOM_PORT_TRACE("HOOK: read %u mission %d: pause, ABORT", g_reads, g_mission);
                queue(g_reads + 1, B_START);
                g_pause_target = 1;
                g_pause_from = g_reads + 40;
            }
            else
            {
                CZSealBody *player = ftsGetPlayer();
                int level = player != NULL ? player->HandleFallingDamage(300.0f) : -1;
                SOCOM_PORT_TRACE("HOOK: read %u mission %d: fatal fall level %d health %.2f alive %d", g_reads, g_mission, level,
                    player != NULL ? player->m_health : 0.0f, player != NULL ? (int)player->m_isAlive : -1);
            }
        }
    }

    /* the pause menu: DOWN until the wanted row, then CROSS */
    if (g_pause_target >= 0 && g_reads >= g_pause_from && g_reads >= g_pause_next && theHUD != NULL && theHUD->m_pausetest.m_on)
    {
        if (theHUD->m_pausetest.m_curselection != g_pause_target)
        {
            queue(g_reads + 1, B_DOWN);
        }
        else
        {
            SOCOM_PORT_TRACE("HOOK: read %u pause menu row %d: CROSS", g_reads, g_pause_target);
            queue(g_reads + 1, B_CROSS);
            g_pause_target = -1;
        }

        g_pause_next = g_reads + 10;
    }
}

unsigned short pressed_now()
{
    unsigned short bits = 0;

    for (int i = 0; i < g_nqueue; i++)
    {
        if (g_reads >= g_queue[i].at && g_reads < g_queue[i].at + 3)
        {
            bits |= g_queue[i].bits;

            if (g_reads == g_queue[i].at)
                SOCOM_PORT_TRACE("HOOK: read %u press %04x (top %s, dialog %s, mission %d)", g_reads, g_queue[i].bits,
                    name_of(g_top), g_dialog.c_str(), g_mission);
        }
    }

    return bits;
}
}

extern "C" void __real__ZN8CMission14OnMissionStartEv(CMission *mission);

extern "C" void __wrap__ZN8CMission14OnMissionStartEv(CMission *mission)
{
    __real__ZN8CMission14OnMissionStartEv(mission);
    g_new_mission = true;
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port == 0)
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

    return r;
}

#ifdef SOCOM_HOOK_MALLOC
/* Every request that fails or moves the program break by 32 KB or more is traced with its tag: the
 * game's _malloc / _calloc / _memalign / _strdup / _new / _new_vec file:line when it came through
 * those, else the caller's address. The guard keeps the trace's own allocations out. */
static int g_in_malloc_trace;
static const char *g_file;
static int g_line;

static void *note(const char *what, size_t size, size_t align, void *p, void *before, void *caller)
{
    if (g_in_malloc_trace || size == 0)
        return p;

    char *after = (char *)sbrk(0);

    if (p == NULL || after >= (char *)before + 0x8000)
    {
        g_in_malloc_trace = 1;
        struct mallinfo mi = mallinfo();
        char tag[64];

        if (g_file != NULL)
            snprintf(tag, sizeof(tag), "%s:%d", g_file, g_line);
        else
            snprintf(tag, sizeof(tag), "%p", caller);

        SOCOM_PORT_TRACE("HOOK: %s(%u, align %u) %s: brk %p -> %p (+%u) arena %u in use %u free %u (%s)", what,
            (unsigned)size, (unsigned)align, p == NULL ? "FAILED" : "grew the heap", before, after,
            (unsigned)(after - (char *)before), (unsigned)mi.arena, (unsigned)mi.uordblks, (unsigned)mi.fordblks, tag);
        g_in_malloc_trace = 0;
    }

    return p;
}

extern "C" void *__real_malloc(size_t size);
extern "C" void *__real_memalign(size_t align, size_t size);
extern "C" void *__real_realloc(void *p, size_t size);
extern "C" void *__real_calloc(size_t n, size_t size);

extern "C" void *__wrap_malloc(size_t size) { void *b = sbrk(0); return note("malloc", size, 0, __real_malloc(size), b, __builtin_return_address(0)); }
extern "C" void *__wrap_memalign(size_t align, size_t size) { void *b = sbrk(0); return note("memalign", size, align, __real_memalign(align, size), b, __builtin_return_address(0)); }
extern "C" void *__wrap_realloc(void *p, size_t size) { void *b = sbrk(0); return note("realloc", size, 0, __real_realloc(p, size), b, __builtin_return_address(0)); }
extern "C" void *__wrap_calloc(size_t n, size_t size) { void *b = sbrk(0); return note("calloc", n * size, 0, __real_calloc(n, size), b, __builtin_return_address(0)); }

extern "C" void *__real__Z7_mallocjPKci(size_t n, const char *f, int l);
extern "C" void *__real__Z7_callocjjPKci(size_t a, size_t b, const char *f, int l);
extern "C" void *__real__Z9_memalignjjPKci(size_t a, size_t n, const char *f, int l);
extern "C" char *__real__Z7_strdupPKcS0_i(const char *s, const char *f, int l);
extern "C" void *__real__Z4_newjPKci(size_t n, const char *f, int l);
extern "C" void *__real__Z8_new_vecjPKci(size_t n, const char *f, int l);

#define TAGGED(ret, name, args, call) \
    extern "C" ret __wrap_##name args { const char *sf = g_file; int sl = g_line; g_file = f ? f : "?"; g_line = l; ret r = call; g_file = sf; g_line = sl; return r; }

TAGGED(void *, _Z7_mallocjPKci, (size_t n, const char *f, int l), __real__Z7_mallocjPKci(n, f, l))
TAGGED(void *, _Z7_callocjjPKci, (size_t a, size_t b, const char *f, int l), __real__Z7_callocjjPKci(a, b, f, l))
TAGGED(void *, _Z9_memalignjjPKci, (size_t a, size_t n, const char *f, int l), __real__Z9_memalignjjPKci(a, n, f, l))
TAGGED(char *, _Z7_strdupPKcS0_i, (const char *s, const char *f, int l), __real__Z7_strdupPKcS0_i(s, f, l))
TAGGED(void *, _Z4_newjPKci, (size_t n, const char *f, int l), __real__Z4_newjPKci(n, f, l))
TAGGED(void *, _Z8_new_vecjPKci, (size_t n, const char *f, int l), __real__Z8_new_vecjPKci(n, f, l))

/* the largest block malloc can hand out now (binary search, each probe freed at once) */
static unsigned largest_free()
{
    g_in_malloc_trace = 1;
    unsigned lo = 0, hi = 32u << 20;

    while (hi - lo > 4096)
    {
        unsigned mid = lo + (hi - lo) / 2;
        void *p = __real_malloc(mid);

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

    g_in_malloc_trace = 0;
    return lo;
}

void hook_state_heap_extra(const char *what)
{
    SOCOM_PORT_TRACE("HOOK: heap %s: largest free block %u", what, largest_free());
}
#else
void hook_state_heap_extra(const char *) {}
#endif
#ifdef SOCOM_HOOK_LEAK
/* with port/test-hooks/death/hook_leak.cpp (build.sh: HLEAK=1, without -DSOCOM_HOOK_MALLOC): armed when the
 * first mission load starts, the survivors are listed when the menus load their world after a mission (LoadWorld("ui")) */
extern "C" int socom_hleak_armed;
extern "C" void socom_hleak_dump(const char *when);
extern "C" char *__malloc_sbrk_base;
extern "C" char *__malloc_av_[];
extern "C" int socom_hleak_tag(void *q, uintptr_t *tag, uint32_t *line);

/* newlib's heap, chunk by chunk (dlmalloc: [prev_size][size | PREV_INUSE] user data): the free chunks of 256 KB or
 * more, and every in-use chunk with free chunks of 32 KB or more on both sides (a pin), with its tracker tag */
/* who made the XRef nodes (CNode::CreateXRef, both overloads): node -> caller */
struct XRefMade { void *node; void *caller; };
static XRefMade g_xref[2048];
static unsigned g_nxref;

extern "C" void *__real__ZN3zdb5CNode10CreateXRefEv();
extern "C" void *__real__ZN3zdb5CNode10CreateXRefEPNS_6CModelEPK6CPnt3DPK5CQuat(void *m, const void *p, const void *r);

static void *xref_made(void *node, void *caller)
{
    if (node != NULL)
    {
        g_xref[g_nxref % 2048].node = node;
        g_xref[g_nxref % 2048].caller = caller;
        g_nxref++;
    }

    return node;
}

extern "C" void *__wrap__ZN3zdb5CNode10CreateXRefEv()
{
    return xref_made(__real__ZN3zdb5CNode10CreateXRefEv(), __builtin_return_address(0));
}

extern "C" void *__wrap__ZN3zdb5CNode10CreateXRefEPNS_6CModelEPK6CPnt3DPK5CQuat(void *m, const void *p, const void *r)
{
    return xref_made(__real__ZN3zdb5CNode10CreateXRefEPNS_6CModelEPK6CPnt3DPK5CQuat(m, p, r), __builtin_return_address(0));
}

static void *xref_caller(void *node)
{
    for (unsigned i = 0; i < 2048 && i < g_nxref; i++)
        if (g_xref[i].node == node)
            return g_xref[i].caller;

    return NULL;
}
/* what lies between two free chunks of 256 KB or more: the in-use bytes there by tracker tag (top 4) */
struct SepTag { uintptr_t tag; uint32_t line; uint32_t bytes; uint32_t count; };
static SepTag g_sep[64];
static int g_nsep;
static uint32_t g_sep_bytes, g_sep_untracked;
static char *g_sep_from;

static void separator_add(char *chunk, size_t size)
{
    if (g_sep_from == NULL)
        g_sep_from = chunk;

    g_sep_bytes += size;
    uintptr_t tag = 0;
    uint32_t line = 0;

    if (!socom_hleak_tag(chunk + 8, &tag, &line))
    {
        g_sep_untracked += size;
        return;
    }

    if (void *caller = xref_caller(chunk + 8))
    {
        tag = (uintptr_t)caller; /* an XRef node: tagged by who made it */
        line = 0;
    }

    int k;

    for (k = 0; k < g_nsep; k++)
        if (g_sep[k].tag == tag && g_sep[k].line == line)
            break;

    if (k == g_nsep)
    {
        if (g_nsep == 64)
            return;

        g_sep[k].tag = tag;
        g_sep[k].line = line;
        g_sep[k].bytes = 0;
        g_sep[k].count = 0;
        g_nsep++;
    }

    g_sep[k].bytes += size;
    g_sep[k].count++;
}

static void separator_report(char *free_chunk)
{
    if (g_sep_from != NULL && g_sep_bytes > 0)
    {
        SOCOM_PORT_TRACE("HOOK: walk in use %p..%p: %u bytes, %u untracked (allocated before arming)", g_sep_from, free_chunk,
            g_sep_bytes, g_sep_untracked);

        for (int n = 0; n < 4 && n < g_nsep; n++)
        {
            int best = n;

            for (int k = n + 1; k < g_nsep; k++)
                if (g_sep[k].bytes > g_sep[best].bytes)
                    best = k;

            SepTag s = g_sep[n]; g_sep[n] = g_sep[best]; g_sep[best] = s;

            if (g_sep[n].line != 0)
                SOCOM_PORT_TRACE("HOOK: walk   %u bytes %u chunks %s:%u", g_sep[n].bytes, g_sep[n].count, (const char *)g_sep[n].tag, g_sep[n].line);
            else
                SOCOM_PORT_TRACE("HOOK: walk   %u bytes %u chunks from %p", g_sep[n].bytes, g_sep[n].count, (void *)g_sep[n].tag);
        }
    }

    g_nsep = 0;
    g_sep_bytes = 0;
    g_sep_untracked = 0;
    g_sep_from = NULL;
}
static void heap_walk()
{
    char *top = __malloc_av_[2];
    char *p = NULL;

    for (uintptr_t align = 16; align >= 8 && p == NULL; align /= 2)
    {
        char *c = __malloc_sbrk_base;

        while (((uintptr_t)c + 8) % align != 0)
            c++;

        size_t s = *(size_t *)(c + 4);

        if ((s & 1) != 0 && (s & ~(size_t)3) >= 16 && (s & ~(size_t)3) < (32u << 20))
            p = c;
    }

    if (p == NULL || top == NULL)
    {
        SOCOM_PORT_TRACE("HOOK: walk: no first chunk at %p", __malloc_sbrk_base);
        return;
    }

    SOCOM_PORT_TRACE("HOOK: walk %p .. top %p", p, top);
    unsigned big = 0, pins = 0, chunks = 0, run_count = 0;
    size_t prev_free = 0, run_bytes = 0;
    char *run = NULL;

    while (p < top && chunks < 400000)
    {
        size_t size = *(size_t *)(p + 4) & ~(size_t)3;

        if (size < 16 || p + size > top + 16)
        {
            SOCOM_PORT_TRACE("HOOK: walk stops at %p (size %u)", p, (unsigned)size);
            break;
        }

        char *next = p + size;
        bool inuse = next >= top ? true : (*(size_t *)(next + 4) & 1) != 0;
        chunks++;

        if (!inuse)
        {
            if (size >= 0x40000)
            {
                big++;
                SOCOM_PORT_TRACE("HOOK: walk free %p %u", p, (unsigned)size);
            }

            if (run != NULL && prev_free >= 0x8000 && size >= 0x8000 && run_bytes <= 0x2000 && pins < 100)
            {
                uintptr_t tag = 0;
                uint32_t line = 0;
                int tracked = socom_hleak_tag(run + 8, &tag, &line);
                pins++;

                if (tracked && line != 0)
                    SOCOM_PORT_TRACE("HOOK: walk pin %p %u bytes in %u chunks (free %u before, %u after): first %s:%u", run, (unsigned)run_bytes, run_count, (unsigned)prev_free, (unsigned)size, (const char *)tag, line);
                else
                    SOCOM_PORT_TRACE("HOOK: walk pin %p %u bytes in %u chunks (free %u before, %u after): first %s %p", run, (unsigned)run_bytes, run_count, (unsigned)prev_free, (unsigned)size, tracked ? "from" : "untracked", (void *)tag);
            }

            if (size >= 0x40000)
                separator_report(p);

            prev_free = size;
            run = NULL;
            run_bytes = 0;
            run_count = 0;
        }
        else
        {
            if (run == NULL)
                run = p;

            run_bytes += size;
            run_count++;
            separator_add(p, size);
        }

        p = next;
    }

    separator_report(top);
    SOCOM_PORT_TRACE("HOOK: walk done: %u chunks, %u free >= 256 KB, %u pins", chunks, big, pins);
}
extern "C" bool __real__Z9LoadWorldPKc(const char *name);

/* the menus' world load (CMenuState::Init): the mission is gone by then */
extern "C" bool __wrap__Z9LoadWorldPKc(const char *name)
{
    if (socom_hleak_armed && strcmp(name, "ui") == 0)
    {
        socom_hleak_dump("menus: before LoadWorld(ui)");
        heap_walk();
    }

    return __real__Z9LoadWorldPKc(name);
}
void hook_state_arm() { socom_hleak_armed = 1; }
#else
void hook_state_arm() {}
#endif