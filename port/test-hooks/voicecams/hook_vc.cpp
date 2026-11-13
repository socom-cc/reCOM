/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-voicecams. Wraps scePadRead and drives the pad
 * from the game state (based on boot-leftovers/hook_exit.cpp), and CMission::OnMissionStart:
 *  - cinematic on top: CROSS after 40 reads (skip the movie);
 *  - mission 1: the mission cameras play out (m8bs, m8tut1); 60 reads after the last one ends the
 *    command menu: CIRCLE, CROSS (TEAM), CROSS (row 0, FIRE AT WILL); then the left stick forward
 *    for 8 s, again later; at SOCOM_HOOK_ABORT_AT reads after the start: START, pause row 1
 *    (ABORT), CROSS -> debrief: TRIANGLE -> menus: CROSS, DOWN x5, CROSS (PLAY GAME, START);
 *  - mission 2: SELECT 300 reads in (skip m8bs), again when m8tut1 has played 150 reads; then stay.
 * Traces every state change, every press, the camera's state and a heap/team line every 10 s. */
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

#ifndef SOCOM_HOOK_ABORT_AT
#define SOCOM_HOOK_ABORT_AT 3900
#endif

extern COurGame theGame;
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

namespace
{
enum { B_UP = 0x1000, B_DOWN = 0x4000, B_START = 0x0800, B_SELECT = 0x0100, B_CROSS = 0x0040, B_CIRCLE = 0x0020,
    B_TRIANGLE = 0x0010 };

struct Press
{
    unsigned int at;
    unsigned short bits;
    unsigned int len;
};

Press g_queue[256];
int g_nqueue;
unsigned int g_reads;
const void *g_top;
unsigned int g_top_since;
int g_mission;
unsigned int g_mission_since;
int g_menus;
int g_exit_pressed;
bool g_new_mission;
int g_pause_target = -1;
unsigned int g_pause_from;
unsigned int g_pause_next;
bool g_cam_playing;
int g_cams_seen;
unsigned int g_cam_end;
bool g_orders_queued;
bool g_skip2_done;
unsigned int g_walk_from[4], g_walk_to[4];
int g_nwalk;
unsigned int g_last_trace;

void queue(unsigned int at, unsigned short bits, unsigned int len = 3)
{
    if (g_nqueue < 256)
    {
        g_queue[g_nqueue].at = at;
        g_queue[g_nqueue].bits = bits;
        g_queue[g_nqueue].len = len;
        g_nqueue++;
    }
}

void walk(unsigned int from, unsigned int to)
{
    if (g_nwalk < 4)
    {
        g_walk_from[g_nwalk] = from;
        g_walk_to[g_nwalk] = to;
        g_nwalk++;
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

    if (top != g_top)
    {
        SOCOM_PORT_TRACE("HOOK: read %u state %s -> %s (mission %d)", g_reads, name_of(g_top), name_of(top), g_mission);
        g_top = top;
        g_top_since = g_reads;

        if (top == &theGame.m_menuState)
        {
            g_menus++;

            if (g_menus >= 2 && g_mission == 1)
            {
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
        SOCOM_PORT_TRACE("HOOK: read %u debrief: TRIANGLE (mission %d)", g_reads, g_mission);
        queue(g_reads + 1, B_TRIANGLE);
        g_exit_pressed++;
    }

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

    if (g_new_mission)
    {
        g_new_mission = false;
        g_mission++;
        g_mission_since = g_reads;
        g_cams_seen = 0;
        g_cam_playing = false;
        g_orders_queued = false;
        SOCOM_PORT_TRACE("HOOK: read %u mission %d starts (player %p)", g_reads, g_mission, (void *)ftsGetPlayer());

        if (g_mission == 1)
        {
            unsigned int at = g_reads + SOCOM_HOOK_ABORT_AT;
            queue(at, B_START);
            g_pause_target = 1; /* ABORT */
            g_pause_from = at + 30;
        }
        else if (g_mission == 2)
        {
            queue(g_reads + 300, B_SELECT);
        }
    }

    /* the mission cameras */
    if (top == &theGame.m_coreState && theHUD != NULL && g_mission >= 1)
    {
        bool playing = theHUD->m_missioncams.IsPlaying() != 0;

        if (playing != g_cam_playing)
        {
            CMissionCam *cam = theHUD->m_missioncams.m_currentcam;
            SOCOM_PORT_TRACE("HOOK: read %u (mission t %.1f) mission camera %s %s, letterbox %d, dynamics %d",
                g_reads, theMission.m_timer, playing ? "starts" : "ends",
                playing && cam != NULL ? cam->m_identifier : "", (int)theHUD->m_letterbox.m_slidedir,
                (int)zdb::CCamera::m_dynamics_controlled);
            g_cam_playing = playing;

            if (playing)
                g_cams_seen++;
            else
                g_cam_end = g_reads;

            if (!playing && g_mission == 2 && g_cams_seen == 1 && !g_skip2_done)
            {
                g_skip2_done = true;
                queue(g_reads + 150, B_SELECT); /* m8tut1 starts next: skip it too */
            }
        }

        if (g_mission == 1 && !g_orders_queued && !playing && g_cams_seen >= 2 && g_reads >= g_cam_end + 60)
        {
            g_orders_queued = true;
            /* FIRE AT WILL (no spoken answer in the ELF), then HOLD POSITION (the unit's first seal
             * answers "yes"), later FOLLOW (CAiSFollow confirms: ConfirmAiState) */
            SOCOM_PORT_TRACE("HOOK: read %u orders: TEAM -> FIRE AT WILL, then HOLD POSITION, then FOLLOW", g_reads);
            unsigned int r = g_reads;
            queue(r + 1, B_CIRCLE);
            queue(r + 31, B_CROSS);
            queue(r + 61, B_CROSS);
            walk(r + 150, r + 390);
            queue(r + 450, B_CIRCLE);
            queue(r + 480, B_CROSS);
            queue(r + 500, B_UP);
            queue(r + 520, B_UP);
            queue(r + 540, B_CROSS);
            walk(r + 620, r + 860);
            queue(r + 1100, B_CIRCLE);
            queue(r + 1130, B_CROSS);
            queue(r + 1150, B_UP);
            queue(r + 1170, B_UP);
            queue(r + 1190, B_CROSS);
            walk(r + 1270, r + 1510);
        }
    }

    if (g_reads >= g_last_trace + 300)
    {
        g_last_trace = g_reads;
        CZSealBody *p = ftsGetPlayer();

        if (top == &theGame.m_coreState && p != NULL)
        {
            const CPnt3D *pp = p->GetPosW();
            SOCOM_PORT_TRACE("HOOK: read %u mission %d t %.1f player at %.0f %.0f alive %d headset %p state %d",
                g_reads, g_mission, theMission.m_timer, pp->x, pp->z, (int)p->m_isAlive, (void *)Headset::theHeadset,
                Headset::theHeadset != NULL ? (int)Headset::theHeadset->m_state : -1);
        }
    }
}

unsigned short pressed_now()
{
    unsigned short bits = 0;

    for (int i = 0; i < g_nqueue; i++)
    {
        if (g_reads >= g_queue[i].at && g_reads < g_queue[i].at + g_queue[i].len)
        {
            bits |= g_queue[i].bits;

            if (g_reads == g_queue[i].at)
                SOCOM_PORT_TRACE("HOOK: read %u press %04x (top %s, mission %d)", g_reads, g_queue[i].bits, name_of(g_top), g_mission);
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

        for (int i = 0; i < g_nwalk; i++)
        {
            if (g_reads >= g_walk_from[i] && g_reads < g_walk_to[i])
            {
                rdata[7] = 0; /* left stick forward */

                if (g_reads == g_walk_from[i])
                    SOCOM_PORT_TRACE("HOOK: read %u walk (pad mode 0x%02x)", g_reads, rdata[1]);
            }
        }
    }

    return r;
}
