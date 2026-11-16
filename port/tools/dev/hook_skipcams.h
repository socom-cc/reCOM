/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* hook_skipcams.h (scratch, socom-port-stance): skip the m8 mission cameras (6ab484e: m8bs 21 s, m8tut1
 * 13 s, AI frozen) with SELECT. Include after the game headers; call skipcams_pad(rdata) in the scePadRead
 * wrapper (port 0) and skipcams_busy() in the per-frame script (true: a camera is playing or ended < 60
 * ticks ago, so the script waits). Times are hook_clock.h ticks (1/30 s, real time), so the waits are
 * the same at the missions' 30 fps as they were at 60. */
#ifndef HOOK_SKIPCAMS_H
#define HOOK_SKIPCAMS_H
#include "Apps/FTS/hud/hud.h"
#include "hook_clock.h"

static unsigned int g_sc_reads; /* ticks since the first call (a hook may reset it to 0 per mission) */
static unsigned int g_sc_clock;
static unsigned int g_sc_last_press;
static unsigned int g_sc_last_cam;
static int g_sc_left;

static inline bool skipcams_playing()
{
    return theHUD != NULL && theHUD->m_missioncams.IsPlaying() != 0;
}

static inline void skipcams_pad(unsigned char *rdata)
{
    g_sc_reads += hook_step(&g_sc_clock);

    if (skipcams_playing())
    {
        g_sc_last_cam = g_sc_reads;

        if (g_sc_reads >= g_sc_last_press + 60)
        {
            g_sc_last_press = g_sc_reads;
            g_sc_left = 3;
            SOCOM_PORT_TRACE("HOOK: SELECT skips mission camera %s at tick %u",
                theHUD->m_missioncams.m_currentcam != NULL ? theHUD->m_missioncams.m_currentcam->m_identifier : "-", g_sc_reads);
        }
    }

    /* SELECT held (active low) for 2 ticks (4 fields): one read at 30 fps, two at 60. Longer (the
     * three reads of 60 fps, held at 30) opens the full-screen map, which pauses the game */
    if (g_sc_left > 0 && g_sc_reads < g_sc_last_press + 2)
        rdata[2] &= (unsigned char)~0x01;
    else
        g_sc_left = 0;
}

static inline bool skipcams_busy()
{
    return skipcams_playing() || (g_sc_last_cam != 0 && g_sc_reads < g_sc_last_cam + 60) || (g_sc_last_cam == 0 && g_sc_reads < 700);
}
#endif
