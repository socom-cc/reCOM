/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-teamhud (from boot-voicecams/hook_vc.cpp). Wraps
 * scePadRead and drives the pad from the game state, and CMission::OnMissionStart:
 *  - cinematic on top: CROSS after 40 reads (skip the movie); each mission camera: SELECT 30 reads in;
 *  - mission 1, 60 reads after the cameras: command menu TEAM -> HOLD POSITION (CIRCLE, CROSS, UP, UP,
 *    CROSS), walk 8 s; +700 reads TEAM -> FOLLOW (same keys); +1300 / +1400 a team-mate (Able, not the
 *    player) takes body damage (DamageBody + UpdateHealth, the real hit path); +1700 Bravo's second
 *    seal dies (HandleFallingDamage(300): the fatal fall damage); at SOCOM_HOOK_REPLAY_AT reads after the
 *    start: START, pause row 3 (REPLAY), CROSS -> mission 2 (cameras skipped), stays.
 * Traces the team panel's rows (name, colour, order text) every 60 reads and on change. */
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
#include <math.h>

#ifndef SOCOM_HOOK_REPLAY_AT
#define SOCOM_HOOK_REPLAY_AT 4400
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
unsigned int g_ev_base;
unsigned int g_last_panel;
unsigned int g_last_panel_full;
char g_last_line[512];

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
            unsigned int at = g_reads + SOCOM_HOOK_REPLAY_AT;
            queue(at, B_START);
            g_pause_target = 3; /* REPLAY */
            g_pause_from = at + 30;
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
            {
                g_cams_seen++;
                queue(g_reads + 30, B_SELECT); /* skip the camera */
            }
            else
                g_cam_end = g_reads;
        }

        if (g_mission == 1 && !g_orders_queued && !playing && g_cams_seen >= 2 && g_reads >= g_cam_end + 60)
        {
            g_orders_queued = true;
            SOCOM_PORT_TRACE("HOOK: read %u orders: TEAM -> HOLD POSITION, later TEAM -> FOLLOW", g_reads);
            unsigned int r = g_reads;
            g_ev_base = r;
            queue(r + 1, B_CIRCLE);
            queue(r + 31, B_CROSS);
            queue(r + 51, B_UP);
            queue(r + 71, B_UP);
            queue(r + 91, B_CROSS);
            walk(r + 150, r + 390);
            queue(r + 700, B_CIRCLE);
            queue(r + 730, B_CROSS);
            queue(r + 750, B_UP);
            queue(r + 770, B_UP);
            queue(r + 790, B_CROSS);
        }
    }

    if (g_ev_base != 0 && g_mission == 1 && top == &theGame.m_coreState && theHUD != NULL)
    {
        CTeamNames &tn = theHUD->m_teamnames;
        CZSealBody *player = ftsGetPlayer();

        if (g_reads == g_ev_base + 1300 || g_reads == g_ev_base + 1400)
        {
            for (int i = 0; i < 2; i++)
            {
                CZSealBody *b = tn.m_ally[i];

                if (b != NULL && b != player && b->m_isAlive)
                {
                    f32 before = b->m_health;
                    bool hit = b->DamageBody(b->m_body_healthMax * 0.45f, 1.0f);
                    b->UpdateHealth(DAMAGE_LOCATION::BODY, SEAL_DEATH_TYPE::DEATH_NONE);
                    SOCOM_PORT_TRACE("HOOK: read %u row %d %s hit (DamageBody %d): health %.3f -> %.3f, body %.1f/%.1f",
                        g_reads, i, b->m_display_name ? b->m_display_name : "?", (int)hit, before, b->m_health,
                        b->m_body_health, b->m_body_healthMax);
                    break;
                }
            }
        }

        if (g_reads == g_ev_base + 1700)
        {
            CZSealBody *b = tn.m_ally[3];

            if (b != NULL && b != player && b->m_isAlive)
            {
                int level = b->HandleFallingDamage(300.0f);
                SOCOM_PORT_TRACE("HOOK: read %u row 3 %s fatal fall (level %d): alive %d health %.3f", g_reads,
                    b->m_display_name ? b->m_display_name : "?", level, (int)b->m_isAlive, b->m_health);
            }
        }
    }

    if (theHUD != NULL && top == &theGame.m_coreState && g_reads >= g_last_panel + 60)
    {
        g_last_panel = g_reads;
        CTeamNames &tn = theHUD->m_teamnames;
        char line[512];
        int n = 0;

        for (int i = 0; i < 4; i++)
        {
            CZSealBody *b = tn.m_ally[i];
            const char *name = tn.m_teamname[i].m_string != NULL ? tn.m_teamname[i].m_string : "-";
            const char *order = tn.m_order[i].m_string != NULL ? tn.m_order[i].m_string : "-";
            n += snprintf(line + n, sizeof(line) - n, " | %d %s col %.0f/%.0f/%.0f name %.0f/%.0f/%.0f %s%s h %.2f%s",
                i, name, tn.m_allycolor[i].x, tn.m_allycolor[i].y, tn.m_allycolor[i].z,
                tn.m_teamname[i].m_color.x, tn.m_teamname[i].m_color.y, tn.m_teamname[i].m_color.z,
                order, tn.m_order[i].m_on ? "(on)" : "(off)", b != NULL ? b->m_health : -1.0f,
                b != NULL && !b->m_isAlive ? " DEAD" : "");

            if (n >= (int)sizeof(line) - 1)
                break;
        }

        if (strcmp(line, g_last_line) != 0 || g_reads >= g_last_panel_full + 600)
        {
            g_last_panel_full = g_reads;
            strncpy(g_last_line, line, sizeof(g_last_line) - 1);
            SOCOM_PORT_TRACE("HOOK: read %u m%d t %.1f panel on %d%s", g_reads, g_mission, theMission.m_timer,
                (int)tn.m_on, line);
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
