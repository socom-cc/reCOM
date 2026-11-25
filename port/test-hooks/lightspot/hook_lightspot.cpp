/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): the player put at a given world position once the mission cameras are
 * over, to screenshot the same spot in two builds (the position as the game's own status line
 * shows it, the -f option). Wraps CZSealBody::GetTerrainMotionFactor (called per seal frame
 * across units, so --wrap sees it). The player's health is kept full, and every 30 player frames
 * the hook traces where he stands and how many local lights the last lit draw carried. */
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zVisual/zvis.h"
#include "Apps/FTS/hud/hud.h"

#ifndef SOCOM_HOOK_HEADING
#define SOCOM_HOOK_HEADING 0.0f /* radians about Y */
#endif

extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    static int quiet = 0;   /* player frames in a row without a mission camera */
    static int placed = 0;  /* player frames since the move */

    if (body != NULL && body == ftsGetPlayer())
    {
        if (body->m_isAlive)
            body->m_health = 1.0f;

        bool camera = theHUD == NULL || theHUD->m_missioncams.IsPlaying() != 0;
        quiet = camera ? 0 : quiet + 1;

        if (placed == 0 && quiet >= 90)
        {
            CPnt3D at(SOCOM_HOOK_X, SOCOM_HOOK_Y, SOCOM_HOOK_Z);
            CQuat turn;
            turn.MakeYRot(SOCOM_HOOK_HEADING);

            /* the floor under the position, looked for from just above it (not from the roof) */
            CPnt3D probe(at.x, at.y + 6.0f, at.z);
            float keep_alt = body->m_alt;
            body->m_alt = probe.y;
            zdb::IntersectStruct *ground = body->SealGetAltitude(&probe, 1.0f);
            body->m_alt = keep_alt;

            if (ground != NULL)
                at.y = ground->m_pos.y;

            body->TeleportTo(&at, &turn);
            body->m_alt = at.y;

            if (ground != NULL)
            {
                body->m_last_altitude.m_pos = ground->m_pos;
                body->m_last_altitude.m_norm = ground->m_norm;
                body->m_last_altitude.m_poly = ground->m_poly;
                body->m_last_altitude.m_node = ground->m_node;
            }

            placed = 1;
            SOCOM_PORT_TRACE("HOOK: lightspot placed at %.0f %.0f %.0f (floor %s)", at.x, at.y, at.z, ground != NULL ? "found" : "not found");
        }
        else if (placed != 0)
        {
            if ((placed++ % 30) == 0)
                SOCOM_PORT_TRACE("HOOK: lightspot player at %.0f %.0f %.0f, last lit draw %d local lights", body->GetPosW()->x,
                    body->GetPosW()->y, body->GetPosW()->z, zdb::CVisual::m_local_light_cnt);
        }
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
