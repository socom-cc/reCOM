/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only) for the AI event / pursue tests. Wraps
 * CameraZoom::AttachSeal (mission start): the nearest enemy is put SOCOM_HOOK_ENEMY in front of
 * the player, the next enemy SOCOM_HOOK_SECOND further on to the side (to hear the shots); the
 * player and both enemies are made invincible so the fight lasts. Wraps
 * CZSealBody::GetTerrainMotionFactor (per player frame): at SOCOM_HOOK_HIDE frames after the
 * start the player is moved SOCOM_HOOK_AWAY behind himself (out of sight), and from then on
 * the test camera (port/tools/dev/hook_freecam.h) looks at the first enemy for
 * SOCOM_HOOK_CAM frames; a trace every 30 frames of both enemies' AI state. */
#include <map>
#include <string>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zGrid/zgrid.h"
#include "gamez/zIntersect/zintersect.h"
#include "gamez/zAI/zai.h"
#include <string.h>
#include <math.h>
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"

#ifndef SOCOM_HOOK_ENEMY
#define SOCOM_HOOK_ENEMY 70.0f
#endif
#ifndef SOCOM_HOOK_SECOND
#define SOCOM_HOOK_SECOND 120.0f
#endif
#ifndef SOCOM_HOOK_HIDE
#define SOCOM_HOOK_HIDE 240
#endif
#ifndef SOCOM_HOOK_AWAY
#define SOCOM_HOOK_AWAY 450.0f
#endif
#ifndef SOCOM_HOOK_CAM
#define SOCOM_HOOK_CAM 1500
#endif

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);

namespace
{
CZSealBody *g_seals[64];
int g_nseals;
CZSealBody *g_enemy;
CZSealBody *g_enemy2;
int g_start = -1;

void walk(zdb::CNode *node, int depth)
{
    if (node == NULL || depth > 3)
        return;

    CZSealBody *seal = CZSealBody::GetSeal(node);

    if (seal != NULL)
    {
        for (int i = 0; i < g_nseals; i++)
            if (g_seals[i] == seal)
                return;

        if (g_nseals < 64)
            g_seals[g_nseals++] = seal;

        return;
    }

    for (zdb::CNodeVector::iterator it = node->m_child.begin(); it != node->m_child.end(); ++it)
        walk(*it, depth + 1);
}

void place(CZSealBody *seal, const CPnt3D &at, const CPnt3D &face)
{
    zdb::CWorld *world = zdb::CWorld::m_world;
    CPnt3D target = at;
    CPnt3D probe(at.x, at.y + 60.0f, at.z);
    bool was = seal->m_node->SetActive(false);
    zdb::IntersectStruct *ground = world->GetAltitude(&probe, 100000.0f);
    seal->m_node->SetActive(was);

    if (ground != NULL)
        target.y = ground->m_pos.y;

    CPnt3D dir(face.x - at.x, 0.0f, face.z - at.z);
    float base = atan2f(dir.x, dir.z);
    float candidates[4] = { base, -base, base + 3.1415927f, -base + 3.1415927f };
    CQuat turn;
    float score = -1e9f;

    for (int k = 0; k < 4; k++)
    {
        CQuat q;
        q.MakeYRot(candidates[k]);
        CMatrix m;
        q.ToMatrix(&m);
        float sc = -m.m_matrix[2][0] * dir.x - m.m_matrix[2][2] * dir.z;

        if (sc > score)
        {
            score = sc;
            turn = q;
        }
    }

    seal->TeleportTo(&target, &turn);
}

void trace_ai(int frame, CZSealBody *s, const char *tag)
{
    if (s == NULL)
        return;

    CSealCtrlAi *ai = static_cast<CSealCtrl *>(s->m_control)->GetSealCtrlAi();

    if (ai == NULL)
        return;

    CAiState *st = ai->GetAiState();
    CEntity *t = ai->m_target.m_target.m_ent;
    SOCOM_PORT_TRACE("HOOK: f%d %s %s at %.0f %.0f %.0f alive %d state %d/%s phase %d aware %d target %s vis %d since %.1f last %.0f %.0f mode %d path %d", frame, tag,
        s->m_node->m_name, s->GetPosW()->x, s->GetPosW()->y, s->GetPosW()->z, (int)s->m_isAlive, (int)st->m_state, st->GetStatus(), (int)st->m_substate,
        (int)ai->GetAiAware(), t != NULL ? t->m_node->m_name : "-", (int)ai->m_target.m_target.m_visible, ai->m_target.GetTimeSinceLastSighting(),
        ai->m_target.m_last_pos.x, ai->m_target.m_last_pos.z, (int)ai->m_mode, (int)ai->m_path.m_state);
}
}

extern "C" void __wrap__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal)
{
    __real__ZN10CameraZoom10AttachSealEP10CZSealBody(seal);
    CZSealBody *player = ftsGetPlayer();
    zdb::CWorld *world = zdb::CWorld::m_world;

    if (player == NULL || world == NULL)
        return;

    g_nseals = 0;
    walk(world, 0);
    CPnt3D me = *player->GetPosW();
    const CMatrix &pm = player->m_node->m_matrix;
    CPnt3D fwd(-pm.m_matrix[2][0], 0.0f, -pm.m_matrix[2][2]);
    float fl = sqrtf(fwd.x * fwd.x + fwd.z * fwd.z);
    fwd.x /= fl; fwd.z /= fl;
    CPnt3D right(-fwd.z, 0.0f, fwd.x);
    CZSealBody *e1 = NULL, *e2 = NULL;
    float d1 = 1e30f, d2 = 1e30f;

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];

        if (s == player || (s->m_team & player->m_team) != 0 || !s->m_isAlive)
            continue;

        CPnt3D p = *s->GetPosW();
        float d = (p.x - me.x) * (p.x - me.x) + (p.z - me.z) * (p.z - me.z);

        if (d < d1) { d2 = d1; e2 = e1; d1 = d; e1 = s; }
        else if (d < d2) { d2 = d; e2 = s; }
    }

    g_enemy = e1;
    g_enemy2 = e2;
    player->m_invincible = 1;

    if (e1 != NULL)
    {
        CPnt3D at(me.x + fwd.x * SOCOM_HOOK_ENEMY, me.y, me.z + fwd.z * SOCOM_HOOK_ENEMY);
        place(e1, at, me);
        e1->m_invincible = 1;
        SOCOM_PORT_TRACE("HOOK: enemy %s to %.0f %.0f %.0f", e1->m_node->m_name, e1->GetPosW()->x, e1->GetPosW()->y, e1->GetPosW()->z);
    }

    if (e2 != NULL)
    {
        CPnt3D at(me.x + fwd.x * (SOCOM_HOOK_ENEMY + SOCOM_HOOK_SECOND) + right.x * 60.0f, me.y, me.z + fwd.z * (SOCOM_HOOK_ENEMY + SOCOM_HOOK_SECOND) + right.z * 60.0f);
        CPnt3D away(at.x + fwd.x * 100.0f, at.y, at.z + fwd.z * 100.0f); /* facing away from the player */
        place(e2, at, away);
        e2->m_invincible = 1;
        SOCOM_PORT_TRACE("HOOK: enemy2 %s to %.0f %.0f %.0f", e2->m_node->m_name, e2->GetPosW()->x, e2->GetPosW()->y, e2->GetPosW()->z);
    }
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer() && g_enemy != NULL)
    {
        static int frame = 0;
        frame++;

        if (frame == SOCOM_HOOK_HIDE)
        {
            CPnt3D me = *body->GetPosW();
            CPnt3D ep = *g_enemy->GetPosW();
            CPnt3D away(me.x - ep.x, 0.0f, me.z - ep.z);
            float l = sqrtf(away.x * away.x + away.z * away.z);
            away.x /= l; away.z /= l;
            CPnt3D at(me.x + away.x * SOCOM_HOOK_AWAY, me.y, me.z + away.z * SOCOM_HOOK_AWAY);
            place(body, at, ep);
            SOCOM_PORT_TRACE("HOOK: f%d player hidden to %.0f %.0f %.0f", frame, body->GetPosW()->x, body->GetPosW()->y, body->GetPosW()->z);
            int k = 0;

            for (int i = 0; i < g_nseals; i++)
            {
                CZSealBody *s = g_seals[i];

                if (s == body || (s->m_team & body->m_team) == 0 || !s->m_isAlive)
                    continue;

                k++;
                CPnt3D near(at.x + away.x * 15.0f * k - away.z * 10.0f, at.y, at.z + away.z * 15.0f * k + away.x * 10.0f);
                place(s, near, ep);
                SOCOM_PORT_TRACE("HOOK: mate %s hidden too", s->m_node->m_name);
            }
            freecam_node(g_enemy->m_node, 0.0f, 90.0f, 140.0f);
        }

        if (frame == SOCOM_HOOK_HIDE + SOCOM_HOOK_CAM)
            freecam_off();

        if (frame % 30 == 0)
        {
            trace_ai(frame, g_enemy, "e1");
            trace_ai(frame, g_enemy2, "e2");
        }
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
