/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): wraps CameraZoom::AttachSeal (cross-unit, so
 * --wrap sees it). Census of the characters (seal nodes under the world: team, alive, position,
 * box DIs on their parts), then the nearest enemy is put SOCOM_HOOK_ENEMY in front of the
 * player (facing him) and the nearest teammate SOCOM_HOOK_MATE in front, SOCOM_HOOK_SIDE to the
 * right. Also wraps CZSealBody::GetReticuleSeal (BitmapReticule::UpdateColor, HUD unit) to trace
 * the reticle's seal when it changes. */
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
#include <string.h>

#ifndef SOCOM_HOOK_ENEMY
#define SOCOM_HOOK_ENEMY 40.0f
#endif
#ifndef SOCOM_HOOK_MATE
#define SOCOM_HOOK_MATE 25.0f
#endif
#ifndef SOCOM_HOOK_SIDE
#define SOCOM_HOOK_SIDE 20.0f
#endif

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" CZSealBody *__real__ZN10CZSealBody15GetReticuleSealEv(CZSealBody *body);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);
#ifndef SOCOM_HOOK_MOVE_FRAME
#define SOCOM_HOOK_MOVE_FRAME 900
#endif

namespace
{
CZSealBody *g_seals[64];
int g_nseals;
CZSealBody *g_enemy;
CZSealBody *g_mate;

int count_dis(zdb::CNode *node, int depth, int *boxes)
{
    if (node == NULL || depth > 30)
        return 0;

    int n = 0;

    for (zdb::CDIVector::iterator it = node->m_di.begin(); it != node->m_di.end(); ++it)
    {
        n++;

        if (dynamic_cast<zdb::CDIBBox *>(*it) != NULL)
            (*boxes)++;
    }

    for (zdb::CNodeVector::iterator it = node->m_child.begin(); it != node->m_child.end(); ++it)
        n += count_dis(*it, depth + 1, boxes);

    return n;
}

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
    CZSealBody *enemy = NULL, *mate = NULL;
    float de = 1e30f, dm = 1e30f;

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];
        CPnt3D p = *s->GetPosW();
        float dx = p.x - me.x, dz = p.z - me.z;
        float d2 = dx * dx + dz * dz;
        int boxes = 0;
        int dis = count_dis(s->m_node, 0, &boxes);
        SOCOM_PORT_TRACE("HOOK: seal %d %s team %x alive %d pos %.0f %.0f %.0f dist %.0f hasDI %d DIs %d boxes %d health %.2f%s", i,
            s->m_node->m_name != NULL ? s->m_node->m_name : "-", s->m_team, (int)s->m_isAlive, p.x, p.y, p.z, sqrtf(d2),
            (int)s->m_node->m_hasDI, dis, boxes, s->m_health, s == player ? " (player)" : "");

        if (s == player)
            continue;

        if ((s->m_team & player->m_team) == 0)
        {
            if (d2 < de) { de = d2; enemy = s; }
        }
        else if (d2 < dm)
        {
            dm = d2;
            mate = s;
        }
    }

    if (player->m_body_parts.size() > 0)
    {
        for (std::vector<CZBodyPart *>::iterator it = player->m_body_parts.begin(); it != player->m_body_parts.end(); ++it)
        {
            CZBodyPart *part = *it;

            if (part == NULL || part->m_node == NULL)
                continue;

            const CBBox &b = part->m_node->m_bbox;
            SOCOM_PORT_TRACE("HOOK: part %s id %d bbox %.1f %.1f %.1f .. %.1f %.1f %.1f DIs %d useparent %d", part->m_node->m_name != NULL ? part->m_node->m_name : "-",
                (int)part->m_id, b.m_min.x, b.m_min.y, b.m_min.z, b.m_max.x, b.m_max.y, b.m_max.z, (int)part->m_node->m_di.size(),
                (int)part->m_node->m_use_parent_bbox);
        }
    }

    g_enemy = enemy;
    g_mate = mate;

    if (enemy != NULL)
    {
        CPnt3D at(me.x + fwd.x * SOCOM_HOOK_ENEMY, me.y, me.z + fwd.z * SOCOM_HOOK_ENEMY);
        place(enemy, at, me);
        SOCOM_PORT_TRACE("HOOK: enemy %s to %.0f %.0f %.0f", enemy->m_node->m_name, enemy->GetPosW()->x, enemy->GetPosW()->y, enemy->GetPosW()->z);
    }

#ifdef SOCOM_HOOK_BEHIND
    /* another teammate SOCOM_HOOK_BEHIND behind the player: between him and the camera */
    CZSealBody *back = NULL;
    float db = 1e30f;

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];

        if (s == player || s == mate || (s->m_team & player->m_team) == 0)
            continue;

        CPnt3D p = *s->GetPosW();
        float d2 = (p.x - me.x) * (p.x - me.x) + (p.z - me.z) * (p.z - me.z);

        if (d2 < db) { db = d2; back = s; }
    }

    if (back != NULL)
    {
        CPnt3D at(me.x - fwd.x * SOCOM_HOOK_BEHIND, me.y, me.z - fwd.z * SOCOM_HOOK_BEHIND);
        place(back, at, me);
        SOCOM_PORT_TRACE("HOOK: behind %s to %.0f %.0f %.0f", back->m_node->m_name, back->GetPosW()->x, back->GetPosW()->y, back->GetPosW()->z);
    }
#endif

    if (mate != NULL)
    {
        CPnt3D at(me.x + fwd.x * SOCOM_HOOK_MATE + right.x * SOCOM_HOOK_SIDE, me.y, me.z + fwd.z * SOCOM_HOOK_MATE + right.z * SOCOM_HOOK_SIDE);
        place(mate, at, me);
        SOCOM_PORT_TRACE("HOOK: mate %s to %.0f %.0f %.0f", mate->m_node->m_name, mate->GetPosW()->x, mate->GetPosW()->y, mate->GetPosW()->z);
    }
}

extern "C" CZSealBody *__wrap__ZN10CZSealBody15GetReticuleSealEv(CZSealBody *body)
{
    CZSealBody *seal = __real__ZN10CZSealBody15GetReticuleSealEv(body);
    static CZSealBody *last = (CZSealBody *)1;

    if (seal != last)
    {
        zdb::CNode *node = body->m_last_reticule.m_node;
        SOCOM_PORT_TRACE("HOOK: reticle seal %s (team %x, alive %d) hit node %s at %.1f %.1f %.1f", seal != NULL && seal->m_node->m_name != NULL ? seal->m_node->m_name : "-",
            seal != NULL ? seal->m_team : 0, seal != NULL ? (int)seal->m_isAlive : -1, node != NULL && node->m_name != NULL ? node->m_name : "-",
            body->m_last_reticule.m_pos.x, body->m_last_reticule.m_pos.y, body->m_last_reticule.m_pos.z);
        last = seal;
    }

    return seal;
}

/* per player frame: at SOCOM_HOOK_MOVE_FRAME the teammate is put 30 in front of the player
 * (facing him), so the scripted walk runs into him; a trace every 15 frames of the player /
 * teammate / enemy state and the player's target list */
extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer())
    {
        static int frame = 0;
        frame++;
        CPnt3D me = *body->GetPosW();

        if (frame == SOCOM_HOOK_MOVE_FRAME && g_mate != NULL)
        {
            const CMatrix &pm = body->m_node->m_matrix;
            CPnt3D fwd(-pm.m_matrix[2][0], 0.0f, -pm.m_matrix[2][2]);
            float fl = sqrtf(fwd.x * fwd.x + fwd.z * fwd.z);
            fwd.x /= fl; fwd.z /= fl;
            CPnt3D at(me.x + fwd.x * 30.0f, me.y, me.z + fwd.z * 30.0f);
            place(g_mate, at, me);
            SOCOM_PORT_TRACE("HOOK: frame %d mate %s moved to %.0f %.0f %.0f", frame, g_mate->m_node->m_name, g_mate->GetPosW()->x, g_mate->GetPosW()->y, g_mate->GetPosW()->z);
        }

        if (frame % 15 == 0)
        {
            float best = 1e30f;
            const char *bestname = "-";

            for (CTargetList::iterator it = body->m_targets.begin(); it != body->m_targets.end(); ++it)
            {
                if (it->m_distSq < best)
                {
                    best = it->m_distSq;
                    bestname = it->m_ent != NULL && it->m_ent->m_node != NULL ? it->m_ent->m_node->m_name : "-";
                }
            }

            CPnt3D mp = g_mate != NULL ? *g_mate->GetPosW() : CPnt3D(0.0f, 0.0f, 0.0f);
            float dm = sqrtf((mp.x - me.x) * (mp.x - me.x) + (mp.z - me.z) * (mp.z - me.z));
            SOCOM_PORT_TRACE("HOOK: f%d player %.1f %.1f %.1f check %d targets %d nearest %s %.1f; mate %.1f %.1f dist %.1f state %d check %d; enemy alive %d health %.2f state %d top %d",
                frame, me.x, me.y, me.z, (int)body->m_check_player_collision, (int)body->m_targets.size(), bestname, sqrtf(best),
                mp.x, mp.z, dm, g_mate != NULL ? (int)g_mate->m_state : -1, g_mate != NULL ? (int)g_mate->m_check_player_collision : -1,
                g_enemy != NULL ? (int)g_enemy->m_isAlive : -1, g_enemy != NULL ? g_enemy->m_health : -1.0f,
                g_enemy != NULL ? (int)g_enemy->m_state : -1, g_enemy != NULL && g_enemy->m_blends->Top() != NULL ? (int)g_enemy->m_blends->Top()->m_animType : -2);
        }
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
