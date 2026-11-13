/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): wraps CZSealBody::GetTerrainMotionFactor (called
 * from another unit each frame for a moving/standing seal). At the player's frame
 * SOCOM_HOOK_KILL_FRAME: with SOCOM_HOOK_KILLER the nearest live enemy seal (no team bit shared
 * with the player) is made the killer through the real CZSealBody::HandleKiller, then the
 * player takes the real fatal fall damage (HandleFallingDamage at impact 300, above the
 * dynamics' level-3 speed 237.5: every part's full health, UpdateHealth -> SetHealth(0) ->
 * OnDeath, the death anim). Every 30 frames a trace of the player's state. */
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zCamera/zcam.h"
#include <math.h>

#ifndef SOCOM_HOOK_KILL_FRAME
#define SOCOM_HOOK_KILL_FRAME 300
#endif

extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer())
    {
        static int frame = 0;
        frame++;

#ifndef SOCOM_HOOK_KILL_FRAME2
#define SOCOM_HOOK_KILL_FRAME2 -1
#endif
        if (frame == SOCOM_HOOK_KILL_FRAME || frame == SOCOM_HOOK_KILL_FRAME2)
        {
#ifdef SOCOM_HOOK_KILLER
            CZSealBody *best = NULL;
            float bd = 1e30f;
            CPnt3D me = *body->GetPosW();

            for (CEntityList::iterator it = CEntity::m_list.begin(); it != CEntity::m_list.end(); ++it)
            {
                CZSealBody *s = SealOfEntity(*it);

                if (s == NULL || s == body || !s->m_isAlive || (s->m_team & body->m_team) != 0)
                    continue;

                CPnt3D p = *s->GetPosW();
                float d = (p.x - me.x) * (p.x - me.x) + (p.z - me.z) * (p.z - me.z);

                if (d < bd)
                {
                    bd = d;
                    best = s;
                }
            }

            if (best != NULL)
            {
                body->HandleKiller(best->m_id);
                SOCOM_PORT_TRACE("HOOK: killer %s (id %d) at %.0f", best->m_node->m_name, (int)best->m_id, sqrtf(bd));
            }
#endif
            int level = body->HandleFallingDamage(300.0f);
            SOCOM_PORT_TRACE("HOOK: frame %d fatal fall: level %d health %.2f alive %d state %d lastkiller %d", frame, level,
                body->m_health, (int)body->m_isAlive, (int)body->m_state, (int)body->m_lastkiller_id);
        }

        if (frame % 30 == 0)
        {
            CPnt3D p = *body->GetPosW();
            SOCOM_PORT_TRACE("HOOK: f%d player %.0f %.0f %.0f state %d alive %d health %.2f", frame, p.x, p.y, p.z,
                (int)body->m_state, (int)body->m_isAlive, body->m_health);
        }
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
