/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): tac-map boots. Wraps CZSealBody::GetTerrainMotionFactor
 * (called per seal frame across units, so --wrap sees it): keeps the player's health full (the
 * m8 enemies rush now) and traces his position every 90 player frames. */
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"

extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    static int frame = 0;

    if (body != NULL && body == ftsGetPlayer())
    {
        if (body->m_isAlive)
            body->m_health = 1.0f;

        if ((frame++ % 90) == 0)
            SOCOM_PORT_TRACE("HOOK: player at %.0f %.0f %.0f alive %d health %.2f", body->GetPosW()->x, body->GetPosW()->y, body->GetPosW()->z, (int)body->m_isAlive, body->m_health);
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
