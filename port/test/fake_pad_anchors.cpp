/* Functional port lane TEST HOOK (off by default): part of SOCOM_PORT_FAKE_PAD (port/CMakeLists.txt,
 * port/compat/libpad.c). Compiled only into fake-pad scratch builds, never into the default build.
 *
 * The anchors a pad script can time its terms from (port/test-hooks/README.md "Pad scripts"): at
 * every fake pad read libpad.c calls socom_fake_poll, which looks at the game's progress and
 * names each point the first time it is seen:
 *   menu      the main menu dlgMenu opened          brief    the m8 briefing dlgAlaska_mission3
 *   dlg<Name> any dialog opened (file name, no .rdr)
 *   load      the load state on top                 movie    the cinematic state on top
 *   core      the mission reached (its state or the intro movie over it on top, once per mission)
 *   debrief   the exit state on top
 *   start     the mission's play begins after its intro movie: the first briefing-camera frame (or
 *             3 s of the mission state on top without a camera)
 *   play      in the mission, the briefing cameras have played and ended (once per mission; known
 *             2 s after the last camera field, which is the anchor's field)
 * It only reads game state (no heap blocks, nothing written), so the game runs as without it. Like
 * the hooks it reaches private members with `#define private public`. Nothing here is game code or
 * evidence for the matching lane. */
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

extern COurGame theGame;
extern "C" void socom_fake_anchor(const char *name);
extern "C" void socom_fake_anchor_at(const char *name, unsigned int field);
extern "C" unsigned int socom_fake_fields(void);

namespace
{
const void *s_top;
char s_dialog[64];
bool s_cams_played;
bool s_play_done;
bool s_in_mission;
bool s_start_done;
unsigned int s_last_cam;
unsigned int s_core_since;

const void *top_state()
{
    const void *top = NULL;

    for (unsigned int i = 0; i < 16; i++)
        if (theGame.m_Stack[i] != NULL)
            top = theGame.m_Stack[i];

    return top;
}
}

extern "C" void socom_fake_poll(void)
{
    const void *top = top_state();

    if (top != s_top)
    {
        s_top = top;
        s_dialog[0] = '\0';

        /* core: the mission's state reached, once per mission (the intro movie is pushed over it
         * at once, so a read can see the movie first) */
        if ((top == &theGame.m_coreState || top == &theGame.m_cinematicSubState) && !s_in_mission)
        {
            s_in_mission = true;
            s_cams_played = false;
            s_play_done = false;
            s_start_done = false;
            s_core_since = 0;
            socom_fake_anchor("core");
        }

        if (top == &theGame.m_loadState)
            socom_fake_anchor("load");
        else if (top == &theGame.m_cinematicSubState)
            socom_fake_anchor("movie");
        else if (top == &theGame.m_exitState)
            socom_fake_anchor("debrief");

        if (top != &theGame.m_coreState && top != &theGame.m_cinematicSubState)
            s_in_mission = false;
    }

    if (top == &theGame.m_menuState && theGame.m_menuState.m_menu != NULL)
    {
        const char *name = theGame.m_menuState.m_menu->m_ReaderName.c_str();

        if (strcmp(name, s_dialog) != 0)
        {
            snprintf(s_dialog, sizeof(s_dialog), "%s", name);
            char stem[64];
            snprintf(stem, sizeof(stem), "%s", name);
            char *dot = strstr(stem, ".rdr");

            if (dot != NULL)
                *dot = '\0';

            if (stem[0] != '\0')
                socom_fake_anchor(stem);

            if (strcmp(stem, "dlgMenu") == 0)
                socom_fake_anchor("menu");
            else if (strcmp(stem, "dlgAlaska_mission3") == 0)
                socom_fake_anchor("brief");
        }
    }

    /* start: the mission's play begins, after its intro movie: the first briefing-camera frame, or
     * 3 s of the mission state on top without one */
    if (top == &theGame.m_coreState && s_in_mission && !s_start_done)
    {
        unsigned int now = socom_fake_fields();

        if (s_core_since == 0)
            s_core_since = now;

        if (theHUD != NULL && theHUD->m_missioncams.IsPlaying() != 0)
        {
            s_start_done = true;
            socom_fake_anchor("start");
        }
        else if (now >= s_core_since + 180)
        {
            s_start_done = true;
            socom_fake_anchor_at("start", s_core_since);
        }
    }
    else if (top != &theGame.m_coreState)
        s_core_since = 0;

    /* play: m8 plays two camera sequences (m8bs 21 s, then m8tut1 13 s) with a short gap, so the
     * cameras count as over after 120 fields (2 s) without one; the anchor's field is the last
     * camera field (terms earlier than play+120 start when it is seen) */
    if (top == &theGame.m_coreState && !s_play_done && theHUD != NULL)
    {
        unsigned int now = socom_fake_fields();

        if (theHUD->m_missioncams.IsPlaying() != 0)
        {
            s_cams_played = true;
            s_last_cam = now;
        }
        else if (s_cams_played && now >= s_last_cam + 120)
        {
            s_play_done = true;
            socom_fake_anchor_at("play", s_last_cam);
        }
    }
}
