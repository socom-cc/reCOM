/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only) for the AI states test (socom-port-aistates).
 * Wraps CameraZoom::AttachSeal (mission start: seal census) and CZSealBody::GetTerrainMotionFactor
 * (per player frame) for three timed tests, each watched by the test camera
 * (port/tools/dev/hook_freecam.h):
 *   door   (SOCOM_HOOK_DOOR_AT): the door action SOCOM_HOOK_DOOR (node name part) is found on the
 *          AI map; the enemy nearest to it is put on the cells SOCOM_HOOK_DOOR_SIDE before it,
 *          and given a route to the cells as far behind it (SetRoute), so the route crosses the
 *          shut door. Camera at the door from the start side.
 *   corpse (SOCOM_HOOK_CORPSE_AT): enemy B is put 50 in front of enemy A (another enemy, not
 *          the door one) and killed 10 frames later; camera on A.
 *   stun   (SOCOM_HOOK_STUN_AT): enemy C gets a flashbang stun (CZSealBody::HandleStunDamage,
 *          type 0, 2.0, the blast 12 in front of its head) - what a Mark141 detonation calls;
 *          camera on C.
 * Every 15 frames during a test the tested AIs' state / phase / mode / path, the door valve.
 * The player is invincible and stays where he starts (far from the tests). */
#include <map>
#include <string>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zNode/node_action.h"
#include "gamez/zGrid/zgrid.h"
#include "gamez/zIntersect/zintersect.h"
#include "gamez/zAI/zai.h"
#include "gamez/zValve/zvalve.h"
#include <string.h>
#include <math.h>
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"

#ifndef SOCOM_HOOK_DOOR
#define SOCOM_HOOK_DOOR "door_depot01"
#endif
#ifndef SOCOM_HOOK_DOOR_SIDE
#define SOCOM_HOOK_DOOR_SIDE 3
#endif
#ifndef SOCOM_HOOK_DOOR_AT
#define SOCOM_HOOK_DOOR_AT 60
#endif
#ifndef SOCOM_HOOK_CORPSE_AT
#define SOCOM_HOOK_CORPSE_AT 1000
#endif
#ifndef SOCOM_HOOK_STUN_AT
#define SOCOM_HOOK_STUN_AT 1700
#endif
#ifndef SOCOM_HOOK_TEST_LEN
#define SOCOM_HOOK_TEST_LEN 600
#endif

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);

namespace
{
CZSealBody *g_seals[64];
int g_nseals;
CZSealBody *g_door_ai, *g_corpse_a, *g_corpse_b, *g_stun_ai;
CNodeAction *g_door;
CPnt3D g_door_pos;
CAiMapLoc g_side_a, g_side_b;
bool g_door_ok;

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
    seal->m_get_new_altitude = 1;
}

CSealCtrlAi *ai_of(CZSealBody *s)
{
    return s != NULL && s->m_control != NULL ? static_cast<CSealCtrl *>(s->m_control)->GetSealCtrlAi() : NULL;
}

void trace_ai(int frame, CZSealBody *s, const char *tag)
{
    CSealCtrlAi *ai = ai_of(s);

    if (ai == NULL)
        return;

    CAiState *st = ai->GetAiState();
    SOCOM_PORT_TRACE("HOOK: f%d %s %s at %.0f %.0f %.0f (%d:%d,%d) alive %d state %d phase %d depth %d aware %d mode %d path %d pts %d stance %d anim %d door %d",
        frame, tag, s->m_node->m_name, s->GetPosW()->x, s->GetPosW()->y, s->GetPosW()->z, s->m_mapLocValid.m_mapid, s->m_mapLocValid.x, s->m_mapLocValid.y,
        (int)s->m_isAlive, (int)st->m_state, (int)st->m_substate, (int)ai->m_stateStack.size(), (int)ai->GetAiAware(), (int)ai->m_mode, (int)ai->m_path.m_state,
        (int)ai->m_path.m_points.size(), (int)ai->m_stance, s->m_blends->Top() != NULL ? (int)s->m_blends->Top()->m_animType : -1,
        g_door != NULL && g_door->m_valve != NULL ? (int)g_door->m_valve->m_value : -1);
}

bool is_enemy(CZSealBody *s, CZSealBody *player)
{
    return s != player && (s->m_team & player->m_team) == 0 && s->m_isAlive && ai_of(s) != NULL;
}

CAiMapLoc loc_at(const CAiMapLoc &base, int dx, int dy)
{
    CAiMapLoc l = base;
    l.x = base.x + dx;
    l.y = base.y + dy;
    return l;
}

bool walkable(const CAiMapLoc &l)
{
    CAiCell *c = AiMaps.GetCell(l);
    return c != NULL && CAiMap::IsWalkable(c) && !c->m_action;
}

void find_door()
{
    for (CNodeAction::Container::iterator it = CNodeAction::m_actions.begin(); it != CNodeAction::m_actions.end(); ++it)
    {
        CNodeAction *a = *it;

        if (a->m_node != NULL && a->m_node->m_name != NULL && strstr(a->m_node->m_name, SOCOM_HOOK_DOOR) != NULL)
        {
            g_door = a;
            break;
        }
    }

    if (g_door == NULL)
    {
        SOCOM_PORT_TRACE("HOOK: door %s not found", SOCOM_HOOK_DOOR);
        return;
    }

    CMatrix world;
    sceVu0UnitMatrix(world.m_matrix);
    g_door->m_node->BuildMTW(world);
    g_door_pos = CPnt3D(world.m_matrix[3][0], world.m_matrix[3][1], world.m_matrix[3][2]);
    CAiMapLoc here;

    if (!AiMaps.GetLocation(&g_door_pos, here))
    {
        SOCOM_PORT_TRACE("HOOK: door %s at %.0f %.0f %.0f off the AI map", g_door->m_node->m_name, g_door_pos.x, g_door_pos.y, g_door_pos.z);
        return;
    }

    for (int r = 0; r <= 6 && !g_door_ok; r++)
    {
        for (int dy = -r; dy <= r && !g_door_ok; dy++)
        {
            for (int dx = -r; dx <= r && !g_door_ok; dx++)
            {
                CAiMapLoc l = loc_at(here, dx, dy);
                CAiCell *c = AiMaps.GetCell(l);

                if (c == NULL || !c->m_action)
                    continue;

                CAiMap::action *act = AiMaps.GetCellAction(l);

                if (act == NULL || act->m_type != 1 || act->m_actionId != g_door->m_id)
                    continue;

                for (int axis = 0; axis < 2 && !g_door_ok; axis++)
                {
                    int k = SOCOM_HOOK_DOOR_SIDE;
                    CAiMapLoc a = axis == 0 ? loc_at(l, -k, 0) : loc_at(l, 0, -k);
                    CAiMapLoc b = axis == 0 ? loc_at(l, k, 0) : loc_at(l, 0, k);

                    if (walkable(a) && walkable(b))
                    {
                        g_side_a = a;
                        g_side_b = b;
                        g_door_ok = true;
                        SOCOM_PORT_TRACE("HOOK: door %s id %d at %.0f %.0f %.0f cell (%d:%d,%d), valve %d; sides (%d,%d) / (%d,%d)", g_door->m_node->m_name,
                            (int)g_door->m_id, g_door_pos.x, g_door_pos.y, g_door_pos.z, l.m_mapid, l.x, l.y, (int)g_door->m_valve->m_value, a.x, a.y, b.x, b.y);
                    }
                }
            }
        }
    }

    if (!g_door_ok)
    {
        SOCOM_PORT_TRACE("HOOK: door %s id %d: no door cell with two open sides near (%d:%d,%d)", g_door->m_node->m_name, (int)g_door->m_id, here.m_mapid, here.x, here.y);

        for (int dy = -8; dy <= 8; dy++)
            for (int dx = -8; dx <= 8; dx++)
            {
                CAiMapLoc l = loc_at(here, dx, dy);
                CAiCell *c = AiMaps.GetCell(l);

                if (c != NULL && c->m_action)
                {
                    CAiMap::action *act = AiMaps.GetCellAction(l);
                    SOCOM_PORT_TRACE("HOOK:   action cell (%d,%d) type %d id %d", l.x, l.y, act != NULL ? (int)act->m_type : -1, act != NULL ? (int)act->m_actionId : -1);
                }
            }
    }
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
    player->m_invincible = 1;
    find_door();
    float best = 1e30f;

    for (int i = 0; i < g_nseals && g_door_ok; i++)
    {
        CZSealBody *s = g_seals[i];

        if (!is_enemy(s, player) || ai_of(s)->m_sleeping)
            continue;

        CPnt3D p = *s->GetPosW();
        float d = (p.x - g_door_pos.x) * (p.x - g_door_pos.x) + (p.z - g_door_pos.z) * (p.z - g_door_pos.z);

        if (d < best)
        {
            best = d;
            g_door_ai = s;
        }
    }

    /* the other tests: the next enemies in census order */
    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];

        if (!is_enemy(s, player) || s == g_door_ai || ai_of(s)->m_sleeping)
            continue;

        if (g_corpse_a == NULL)
            g_corpse_a = s;
        else if (g_corpse_b == NULL)
            g_corpse_b = s;
        else if (g_stun_ai == NULL)
            g_stun_ai = s;
    }

    SOCOM_PORT_TRACE("HOOK: %d seals; door AI %s, corpse %s finds %s, stun %s", g_nseals, g_door_ai != NULL ? g_door_ai->m_node->m_name : "-",
        g_corpse_a != NULL ? g_corpse_a->m_node->m_name : "-", g_corpse_b != NULL ? g_corpse_b->m_node->m_name : "-",
        g_stun_ai != NULL ? g_stun_ai->m_node->m_name : "-");
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer())
    {
        static int frame = 0;
        frame++;

        /* door: the awake enemy nearest to the door (the sleepers are put to sleep after the census) */
        if (g_door_ok && frame == SOCOM_HOOK_DOOR_AT)
        {
            float best = 1e30f;
            g_door_ai = NULL;

            for (int i = 0; i < g_nseals; i++)
            {
                CZSealBody *s = g_seals[i];

                if (!is_enemy(s, body) || ai_of(s)->m_sleeping || s == g_corpse_a || s == g_corpse_b || s == g_stun_ai)
                    continue;

                CPnt3D p = *s->GetPosW();
                float d = (p.x - g_door_pos.x) * (p.x - g_door_pos.x) + (p.z - g_door_pos.z) * (p.z - g_door_pos.z);

                if (d < best)
                {
                    best = d;
                    g_door_ai = s;
                }
            }
        }

        if (g_door_ok && g_door_ai != NULL)
        {
            if (frame == SOCOM_HOOK_DOOR_AT)
            {
                CPnt3D a, b;
                AiMaps.GetCellCenter(g_side_a, &a);
                AiMaps.GetCellCenter(g_side_b, &b);
                place(g_door_ai, a, b);
                g_door_ai->m_invincible = 1;
                SOCOM_PORT_TRACE("HOOK: f%d door AI %s to %.0f %.0f %.0f", frame, g_door_ai->m_node->m_name, a.x, a.y, a.z);
                CPnt3D away(a.x - b.x, 0.0f, a.z - b.z);
                float l = sqrtf(away.x * away.x + away.z * away.z);
                CPnt3D eye(g_door_pos.x + away.x / l * 90.0f + away.z / l * 40.0f, g_door_pos.y + 45.0f, g_door_pos.z + away.z / l * 90.0f - away.x / l * 40.0f);
                freecam_look(eye, g_door_pos);
            }

            if (frame == SOCOM_HOOK_DOOR_AT + 5)
            {
                CSealCtrlAi *dai = ai_of(g_door_ai);
                CAiState *st = dai->GetAiState();

                /* the AI's own script would take the route away (HOLD / GOTO): pause it for the test
                 * (the door anim's script state covers it later and resumes it when done) */
                if (st->m_state == STATE_SCRIPT && static_cast<CAiSScript *>(st)->m_anim != NULL)
                    static_cast<CAiSScript *>(st)->m_anim->Pause();

                bool ok = dai->SetRoute(g_side_b);
                SOCOM_PORT_TRACE("HOOK: f%d door AI route to (%d:%d,%d): %d", frame, g_side_b.m_mapid, g_side_b.x, g_side_b.y, (int)ok);
            }

            if (frame >= SOCOM_HOOK_DOOR_AT && frame < SOCOM_HOOK_DOOR_AT + SOCOM_HOOK_TEST_LEN && frame % 15 == 0)
                trace_ai(frame, g_door_ai, "door");

            if (frame == SOCOM_HOOK_DOOR_AT + SOCOM_HOOK_TEST_LEN)
                freecam_off();
        }

        /* corpse */
        if (g_corpse_a != NULL && g_corpse_b != NULL)
        {
            if (frame == SOCOM_HOOK_CORPSE_AT)
            {
                CPnt3D a = *g_corpse_a->GetPosW();
                const CMatrix &m = g_corpse_a->m_node->m_matrix;
                CPnt3D fwd(-m.m_matrix[2][0], 0.0f, -m.m_matrix[2][2]);
                float l = sqrtf(fwd.x * fwd.x + fwd.z * fwd.z);
                fwd.x /= l; fwd.z /= l;
                CPnt3D at(a.x + fwd.x * 50.0f, a.y, a.z + fwd.z * 50.0f);
                place(g_corpse_b, at, a);
                SOCOM_PORT_TRACE("HOOK: f%d corpse-to-be %s put 50 in front of %s", frame, g_corpse_b->m_node->m_name, g_corpse_a->m_node->m_name);
                freecam_node(g_corpse_a->m_node, -fwd.x * 70.0f + fwd.z * 40.0f, 60.0f, -fwd.z * 70.0f - fwd.x * 40.0f);
            }

            if (frame == SOCOM_HOOK_CORPSE_AT + 10)
            {
                g_corpse_b->SetHealth(0.0f, (SEAL_DEATH_TYPE)0);
                SOCOM_PORT_TRACE("HOOK: f%d %s killed", frame, g_corpse_b->m_node->m_name);
            }

            if (frame >= SOCOM_HOOK_CORPSE_AT && frame < SOCOM_HOOK_CORPSE_AT + SOCOM_HOOK_TEST_LEN && frame % 15 == 0)
                trace_ai(frame, g_corpse_a, "corpse");

            if (frame == SOCOM_HOOK_CORPSE_AT + SOCOM_HOOK_TEST_LEN)
                freecam_off();
        }

        /* stun */
        if (g_stun_ai != NULL)
        {
            if (frame == SOCOM_HOOK_STUN_AT)
            {
                const CMatrix &m = g_stun_ai->m_node->m_matrix;
                CPnt3D fwd(-m.m_matrix[2][0], 0.0f, -m.m_matrix[2][2]);
                float l = sqrtf(fwd.x * fwd.x + fwd.z * fwd.z);
                fwd.x /= l; fwd.z /= l;
                freecam_node(g_stun_ai->m_node, fwd.x * 60.0f + fwd.z * 30.0f, 45.0f, fwd.z * 60.0f - fwd.x * 30.0f);
            }

            if (frame == SOCOM_HOOK_STUN_AT + 20)
            {
                CPnt3D head, dir;
                g_stun_ai->GetHeadParams(&head, &dir);
                const CMatrix &m = g_stun_ai->m_node->m_matrix;
                CPnt3D blast(head.x - m.m_matrix[2][0] * 12.0f, head.y, head.z - m.m_matrix[2][2] * 12.0f);
                SOCOM_PORT_TRACE("HOOK: f%d flashbang at %.0f %.0f %.0f for %s", frame, blast.x, blast.y, blast.z, g_stun_ai->m_node->m_name);
                g_stun_ai->HandleStunDamage(STUN_FLASHBANG, 2.0f, &blast);
            }

            if (frame >= SOCOM_HOOK_STUN_AT && frame < SOCOM_HOOK_STUN_AT + SOCOM_HOOK_TEST_LEN && frame % 15 == 0)
                trace_ai(frame, g_stun_ai, "stun");

            if (frame == SOCOM_HOOK_STUN_AT + SOCOM_HOOK_TEST_LEN)
                freecam_off();
        }
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
