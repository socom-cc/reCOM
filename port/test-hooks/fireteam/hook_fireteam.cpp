/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): fireteam orders and the test camera.
 * Wraps CZSealBody::CheckDIShoot (once a frame, CAppCamera::Tick): on the mission clock
 * (theMission.m_timer) it gives the fireteam (unit 1) the orders a command menu would -
 * HOLDPOS at SOCOM_HOOK_HOLD s, FOLLOW at SOCOM_HOOK_FOLLOW s (CSealUnit::IssueCommand, as
 * OrdersMenu::HandlePad does) - and moves the camera (hook_freecam.h): looking back from the
 * the column from in front of the player (A, C), Bravo holding seen from behind it (B).
 * Every 2 s a trace of the team: position, distance to the player, state. */
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include <string.h>
#include <math.h>
#include "hook_freecam.h"

#ifndef SOCOM_HOOK_HOLD
#define SOCOM_HOOK_HOLD 22.0f
#endif
#ifndef SOCOM_HOOK_FOLLOW
#define SOCOM_HOOK_FOLLOW 38.0f
#endif
#define SOCOM_HOOK_CAM_A0 13.0f
#define SOCOM_HOOK_CAM_A1 20.0f
#define SOCOM_HOOK_CAM_B0 26.0f
#define SOCOM_HOOK_CAM_B1 36.0f
#define SOCOM_HOOK_CAM_C0 44.0f
#define SOCOM_HOOK_CAM_C1 58.0f
#ifndef SOCOM_HOOK_CAM_BACK0
#define SOCOM_HOOK_CAM_BACK0 26.0f
#endif
#ifndef SOCOM_HOOK_CAM_BACK1
#define SOCOM_HOOK_CAM_BACK1 37.0f
#endif
#ifndef SOCOM_HOOK_CAM_TRAIL0
#define SOCOM_HOOK_CAM_TRAIL0 43.0f
#endif
#ifndef SOCOM_HOOK_CAM_TRAIL1
#define SOCOM_HOOK_CAM_TRAIL1 56.0f
#endif

namespace
{
bool g_hold_done;
bool g_follow_done;
float g_last_trace = -10.0f;
const char *g_state_names[30] = {
    "unknown", "script", "hold", "avoid", "deploy", "lasing", "surrender", "restrained", "goto", "follow",
    "breach", "action", "pursue", "animate", "cqb", "flee", "pathreco", "rescued", "suspended", "shotat",
    "reload", "noammo", "pickup", "hostage", "corpse", "event", "targeting", "grenade", "stunned", "rush"
};

void team_trace(CZSealBody *player, float t)
{
    const CPnt3D *pp = player->GetPosW();

    for (std::list<CSealUnit *>::iterator u = CSealUnit::m_list.begin(); u != CSealUnit::m_list.end(); ++u)
    {
        if ((*u)->m_unit_num != 2 && (*u)->m_unit_num != 3)
            continue;

        for (std::list<CZSealBody *>::iterator s = (*u)->m_seals.begin(); s != (*u)->m_seals.end(); ++s)
        {
            CZSealBody *seal = *s;

            if (seal == player)
                continue;

            CSealCtrlAi *ai = static_cast<CSealCtrl *>(seal->m_control)->GetSealCtrlAi();
            const CPnt3D *p = seal->GetPosW();
            float dx = p->x - pp->x, dz = p->z - pp->z;
            CAiState *st = ai != NULL ? ai->GetAiState() : NULL;
            int s8 = st != NULL ? st->m_state : -1;
            SOCOM_PORT_TRACE("HOOK: t%.1f team %s (unit %d) at %.0f %.0f dist %.0f state %s mode %d fmode %d alive %d",
                t, seal->m_node->m_name, (*u)->m_unit_num, p->x, p->z, sqrtf(dx * dx + dz * dz),
                s8 >= 0 && s8 < 30 ? g_state_names[s8] : "-", ai != NULL ? (int)ai->m_mode : -1,
                ai != NULL ? (int)ai->m_followMode : -1, (int)seal->m_isAlive);
        }
    }

    SOCOM_PORT_TRACE("HOOK: t%.1f player at %.0f %.0f", t, pp->x, pp->z);
}
}

extern "C" void __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat);

extern "C" void __wrap__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat)
{
    __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(body, eye, mat);
    CZSealBody *player = ftsGetPlayer();

    if (!CSealUnit::m_created_units_test || player == NULL || !player->m_isAlive)
    {
        freecam_apply();
        return;
    }

    float t = theMission.m_timer;

    if (!g_hold_done && t >= SOCOM_HOOK_HOLD)
    {
        g_hold_done = true;
        SOCOM_PORT_TRACE("HOOK: t%.1f order: fireteam HOLDPOS", t);
        CSealUnit::GetUnitByTeam(1)->IssueCommand(player, CMD_HOLDPOS, NULL, false);
    }

    if (!g_follow_done && t >= SOCOM_HOOK_FOLLOW)
    {
        g_follow_done = true;
        SOCOM_PORT_TRACE("HOOK: t%.1f order: fireteam FOLLOW", t);
        CSealUnit::GetUnitByTeam(1)->IssueCommand(player, CMD_FOLLOW, NULL, false);
    }

    if (t - g_last_trace >= 2.0f)
    {
        g_last_trace = t;
        team_trace(player, t);
    }

    const float *row = player->m_node->m_matrix.m_matrix[2];
    const CPnt3D *pp = player->GetPosW();
    float fx = -row[0], fz = -row[2];
    float fl = sqrtf(fx * fx + fz * fz);

    if (fl > 0.001f)
    {
        fx /= fl;
        fz /= fl;
    }

    CZSealBody *bailey = NULL;
    CSealUnit *bravo = CSealUnit::GetUnitByTeam(3);

    if (bravo != NULL && !bravo->m_seals.empty())
        bailey = bravo->m_seals.front();

    bool front = (t >= SOCOM_HOOK_CAM_A0 && t < SOCOM_HOOK_CAM_A1) || (t >= SOCOM_HOOK_CAM_C0 && t < SOCOM_HOOK_CAM_C1);

    if (front)
    {
        /* in front of the player, low, looking back at him and the team behind him */
        CPnt3D eye(pp->x + fx * 160.0f, pp->y + 70.0f, pp->z + fz * 160.0f);
        CPnt3D target(pp->x - fx * 120.0f, pp->y + 10.0f, pp->z - fz * 120.0f);
        freecam_look(eye, target);
    }
    else if (t >= SOCOM_HOOK_CAM_B0 && t < SOCOM_HOOK_CAM_B1 && bailey != NULL)
    {
        /* behind Bravo's leader (away from the player), looking past Bravo at the player */
        const CPnt3D *bp = bailey->GetPosW();
        float dx = pp->x - bp->x, dz = pp->z - bp->z;
        float dl = sqrtf(dx * dx + dz * dz);

        if (dl > 0.001f)
        {
            dx /= dl;
            dz /= dl;
        }

        CPnt3D eye(bp->x - dx * 110.0f, bp->y + 60.0f, bp->z - dz * 110.0f);
        CPnt3D target(bp->x + dx * 150.0f, bp->y + 10.0f, bp->z + dz * 150.0f);
        freecam_look(eye, target);
    }
    else if (g_freecam.on)
        freecam_off();

    freecam_apply();
}
