/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): wraps CameraZoom::AttachSeal (CCoreState::Init
 * calls it across units, so --wrap sees it). Casts 36 level rays at chest height around the
 * player's start through CWorld::GetIntersect (the new single-ray world intersect), traces the
 * hits, and teleports the player SOCOM_HOOK_GAP units in front of the nearest wall that faces
 * the ray, facing it (SOCOM_HOOK_BACK: facing away), so the scripted stick runs the player into it. */
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zGrid/zgrid.h"
#include "gamez/zIntersect/zintersect.h"
#include "gamez/zGame/zgame.h"
#include <string.h>

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);

extern "C" void __wrap__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal)
{
    __real__ZN10CameraZoom10AttachSealEP10CZSealBody(seal);
    CZSealBody *player = ftsGetPlayer();
    zdb::CWorld *world = zdb::CWorld::m_world;

    if (player == NULL || world == NULL)
        return;

    zdb::CNode *node = player->m_node;
#ifdef SOCOM_HOOK_X
    {
        /* first to x/z on the ground (the m8 grid centre has the mining company building) */
        CPnt3D probe(SOCOM_HOOK_X, 0.0f, SOCOM_HOOK_Z);
        zdb::IntersectStruct *ground = world->GetAltitude(&probe, 100000.0f);
        probe.y = ground != NULL ? ground->m_pos.y : 0.0f;
        player->TeleportTo(&probe, NULL);
        SOCOM_PORT_TRACE("HOOK: player first to %.1f %.1f %.1f", probe.x, probe.y, probe.z);
    }
#endif
    CPnt3D start(node->m_matrix.m_matrix[3][0], node->m_matrix.m_matrix[3][1] + 15.0f, node->m_matrix.m_matrix[3][2]);
    CPnt3D fwd(-node->m_matrix.m_matrix[2][0], 0.0f, -node->m_matrix.m_matrix[2][2]);
    fwd.Normalize();
    bool was = node->SetActive(false);
    float best = 1e9f;
    CPnt3D best_pos;
    CPnt3D best_dir;
    int best_ray = -1;

    for (int i = 0; i < 36; i++)
    {
        float a = (float)i * (6.2831853f / 36.0f);
        CPnt3D dir(fwd.x * cosf(a) - fwd.z * sinf(a), 0.0f, fwd.x * sinf(a) + fwd.z * cosf(a));
        CPnt3D tip(start.x + dir.x * SOCOM_HOOK_RANGE, start.y, start.z + dir.z * SOCOM_HOOK_RANGE);
        zdb::IntersectStruct *hit = world->GetIntersect(&start, &tip);

        if (hit == NULL)
        {
            SOCOM_PORT_TRACE("HOOK: ray %d dir %.2f %.2f: no hit (%d)", i, dir.x, dir.z, world->m_diInt->m_Cnt);
            continue;
        }

        float dx = hit->m_pos.x - start.x;
        float dz = hit->m_pos.z - start.z;
        float dist = sqrtf(dx * dx + dz * dz);
        float facing = hit->m_norm.x * dir.x + hit->m_norm.z * dir.z;
        SOCOM_PORT_TRACE("HOOK: ray %d dir %.2f %.2f: %d hits, nearest %.0f at %.1f %.1f %.1f n %.2f %.2f %.2f node %s", i, dir.x, dir.z,
            world->m_diInt->m_Cnt, dist, hit->m_pos.x, hit->m_pos.y, hit->m_pos.z, hit->m_norm.x, hit->m_norm.y, hit->m_norm.z,
            hit->m_node != NULL && hit->m_node->m_name != NULL ? hit->m_node->m_name : "-");

        bool named = true;
#ifdef SOCOM_HOOK_NAME
        named = hit->m_node != NULL && hit->m_node->m_name != NULL && strstr(hit->m_node->m_name, SOCOM_HOOK_NAME) != NULL;
#endif
        if (named && facing < -0.5f && fabsf(hit->m_norm.y) < 0.4f && dist > SOCOM_HOOK_GAP && dist < best)
        {
            /* head-on: in front of the wall along its level normal, facing into it */
            best = dist;
            best_pos = hit->m_pos;
            best_dir.x = -hit->m_norm.x;
            best_dir.y = 0.0f;
            best_dir.z = -hit->m_norm.z;
            best_dir.Normalize();
            best_ray = i;
        }
    }

    node->SetActive(was);

    if (best_ray < 0)
    {
        SOCOM_PORT_TRACE("HOOK: no wall found; the player stays");
        return;
    }

    CPnt3D target(best_pos.x - best_dir.x * SOCOM_HOOK_GAP, 0.0f, best_pos.z - best_dir.z * SOCOM_HOOK_GAP);
    CPnt3D probe(target.x, 0.0f, target.z);
    zdb::IntersectStruct *ground = world->GetAltitude(&probe, 100000.0f);
    target.y = ground != NULL ? ground->m_pos.y : start.y - 15.0f;
#ifdef SOCOM_HOOK_BACK
    /* back to the wall: face away from it (the camera would sit behind the wall) */
    best_dir.x = -best_dir.x;
    best_dir.z = -best_dir.z;
#endif
    float base = atan2f(best_dir.x, best_dir.z);
    float candidates[4] = { base, -base, base + 3.1415927f, -base + 3.1415927f };
    CQuat turn;
    float score = -2.0f;

    for (int k = 0; k < 4; k++)
    {
        CQuat q;
        q.MakeYRot(candidates[k]);
        CMatrix m;
        q.ToMatrix(&m);
        float s = -m.m_matrix[2][0] * best_dir.x - m.m_matrix[2][2] * best_dir.z;

        if (s > score)
        {
            score = s;
            turn = q;
        }
    }

    player->TeleportTo(&target, &turn);
    SOCOM_PORT_TRACE("HOOK: wall from ray %d at %.0f: player to %.1f %.1f %.1f facing %.2f %.2f (match %.2f)", best_ray, best,
        target.x, target.y, target.z, -node->m_matrix.m_matrix[2][0], -node->m_matrix.m_matrix[2][2], score);
}
