/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-leftovers, part b (leaving a mission from the
 * pause menu, replay). Wraps scePadRead and drives the pad from the game state it sees (the top of
 * theGame's state stack, the player pointer), so no read numbers have to be guessed across loads:
 *  - cinematic on top: CROSS after 40 reads (skip the movie);
 *  - mission n (a new player pointer = a new mission or a replay): after SOCOM_HOOK_PAUSE_AT reads
 *    START (pause menu), then DOWN x1 (ABORT) or x3 (REPLAY), then CROSS;
 *      n=1 ABORT, debrief X (replay: OnPop(1) -> ReOpen_Load);
 *      n=2 pause REPLAY (abort valve 2: the exit state pops 1 without a debrief);
 *      n=3 ABORT, debrief TRIANGLE -> menus -> PLAY GAME, briefing START -> mission 4;
 *      n=4 after SOCOM_HOOK_LAST_AT reads ABORT, debrief TRIANGLE -> menus; then nothing.
 *  - debrief (exit state on top): X / TRIANGLE after 300 reads, again every 150 while on top;
 *  - menus again (not the first time): CROSS +60, DOWN x5 +150.., CROSS +210.
 * Every state change is traced (the trace carries the heap use). */
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
#include <math.h>
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"

#ifndef SOCOM_HOOK_PAUSE_AT
#define SOCOM_HOOK_PAUSE_AT 450
#endif
#ifndef SOCOM_HOOK_LAST_AT
#define SOCOM_HOOK_LAST_AT 900
#endif

extern COurGame theGame;
extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

extern "C" void __wrap__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal)
{
    __real__ZN10CameraZoom10AttachSealEP10CZSealBody(seal);
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}

namespace
{
enum { B_UP = 0x1000, B_DOWN = 0x4000, B_START = 0x0800, B_CROSS = 0x0040, B_TRIANGLE = 0x0010 };

struct Press
{
    unsigned int at;
    unsigned short bits;
};

Press g_queue[128];
int g_nqueue;
unsigned int g_reads;
const void *g_top;
unsigned int g_top_since;
CZSealBody *g_player;
int g_mission;
unsigned int g_mission_since;
int g_menus;
int g_exit_pressed;
bool g_new_mission;
int g_pause_target = -1;  /* pause menu row to reach (DOWN until there, then CROSS) */
unsigned int g_pause_from;
unsigned int g_pause_next;

void queue(unsigned int at, unsigned short bits)
{
    if (g_nqueue < 128)
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

void watch()
{
    const void *top = top_state();

    static const void *prev_top = NULL;

    if (top != g_top)
    {
        prev_top = g_top;
        SOCOM_PORT_TRACE("HOOK: read %u state %s -> %s (depth index %u, mission %d)", g_reads, name_of(g_top), name_of(top),
            (unsigned)theGame.m_CurrentState, g_mission);
        g_top = top;
        g_top_since = g_reads;

        if (top == &theGame.m_menuState)
        {
            g_menus++;

            if (g_menus >= 2 && g_mission == 3)
            {
                /* back at the menus after mission 3: PLAY GAME, the briefing's START */
                queue(g_reads + 60, B_CROSS);

                for (int i = 0; i < 5; i++)
                    queue(g_reads + 150 + 10 * i, B_DOWN);

                queue(g_reads + 210, B_CROSS);
            }
        }
        else if (top == &theGame.m_cinematicSubState)
        {
            queue(g_reads + 40, B_CROSS);
        }
        else if (top == &theGame.m_exitState)
        {
            g_exit_pressed = 0;
        }
    }

    if (top == &theGame.m_exitState && g_reads >= g_top_since + 300 && (g_reads - g_top_since - 300) % 150 == 0 && g_exit_pressed < 4)
    {
        unsigned short bits = g_mission == 1 ? B_CROSS : B_TRIANGLE;
        SOCOM_PORT_TRACE("HOOK: read %u debrief: %s (mission %d)", g_reads, bits == B_CROSS ? "X (replay)" : "TRIANGLE (menus)", g_mission);
        queue(g_reads + 1, bits);
        g_exit_pressed++;
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

    /* a mission starts: CMission::OnMissionStart ran (first load or replay) */
    static const void *before_core = NULL;

    if (g_new_mission)
    {
        g_new_mission = false;
        g_mission++;
        g_mission_since = g_reads;
        SOCOM_PORT_TRACE("HOOK: read %u mission %d starts (player %p)", g_reads, g_mission, (void *)ftsGetPlayer());
        unsigned int at = g_reads + (g_mission == 4 ? SOCOM_HOOK_LAST_AT : SOCOM_HOOK_PAUSE_AT);
        int downs = g_mission == 2 ? 3 : 1;

        if (g_mission <= 4)
        {
            queue(at, B_START);
            g_pause_target = downs == 3 ? 3 : 1; /* REPLAY : ABORT */
            g_pause_from = at + 30;
        }
        (void)downs;
    }

    if (g_top_since == g_reads && top != &theGame.m_coreState)
        before_core = top;
    (void)prev_top;
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
            {
                CZSealBody *p = ftsGetPlayer();
                CSealCtrl *c = p != NULL ? static_cast<CSealCtrl *>(p->m_control) : NULL;
                SOCOM_PORT_TRACE("HOOK: read %u press %04x (top %s, mission %d) input %d pause on %d sel %d owner %p player %p", g_reads,
                    g_queue[i].bits, name_of(g_top), g_mission, c != NULL ? (int)c->m_input_enabled : -1,
                    theHUD != NULL ? (int)theHUD->m_pausetest.m_on : -1, theHUD != NULL ? (int)theHUD->m_pausetest.m_curselection : -1,
                    (void *)CHUD::GetHUDOwner(), (void *)p);
            }
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
    SOCOM_PORT_TRACE("HOOK: CMission::OnMissionStart (player %p)", (void *)ftsGetPlayer());
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
