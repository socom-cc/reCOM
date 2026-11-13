/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): wraps CameraZoom::AttachSeal (called across units,
 * so --wrap sees it). Census of the world's DI polys by app flags (the climb/ladder/step
 * markers ImpactFront dispatches on), with the nearest few of each flag to the player's start
 * (world centre, level normal, height span, node name). With SOCOM_HOOK_FLAG the player is put
 * SOCOM_HOOK_GAP in front of the SOCOM_HOOK_PICK-th nearest poly of that flag (on its normal
 * side, facing it), so the scripted stick walks him into it. */
#include <map>
#include <string>
#include <vector>
#include <list>
#include <unordered_map>
#define protected public /* scratch hook only: reads the body's blend stack and state */
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zGrid/zgrid.h"
#include "gamez/zIntersect/zintersect.h"
#include "gamez/zGame/zgame.h"
#include <string.h>

#ifndef SOCOM_HOOK_PICK
#define SOCOM_HOOK_PICK 0
#endif
#ifndef SOCOM_HOOK_GAP
#define SOCOM_HOOK_GAP 12.0f
#endif

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);

namespace
{
struct DIPeek : zdb::CDI
{
    static CPnt4D *pts(zdb::CDI *d) { return static_cast<DIPeek *>(d)->m_pts; }
};

const int KEEP = 8;

struct Sample
{
    float d2;
    CPnt3D c;
    CPnt3D n;
    float ylo, yhi;
    int pts;
    int ditype, camtype, material;
    const char *name;
};

int g_count[8];
int g_nodes, g_dis, g_polys;
Sample g_best[8][KEEP];
int g_nbest[8];
CPnt3D g_me;

void keep(int f, const Sample &s)
{
    int n = g_nbest[f];
    int i = n < KEEP ? n : KEEP - 1;

    if (n >= KEEP && s.d2 >= g_best[f][KEEP - 1].d2)
        return;

    while (i > 0 && g_best[f][i - 1].d2 > s.d2)
    {
        g_best[f][i] = g_best[f][i - 1];
        i--;
    }

    g_best[f][i] = s;

    if (n < KEEP)
        g_nbest[f]++;
}

void walk(zdb::CNode *node, int depth)
{
    if (node == NULL || depth > 40)
        return;

    g_nodes++;

    for (zdb::CDIVector::iterator it = node->m_di.begin(); it != node->m_di.end(); ++it)
    {
        zdb::CDI *di = *it;
        g_dis++;

        if (di == NULL)
            continue;

        int f = di->m_appflags;
        g_count[f]++;
        CPnt4D *p = DIPeek::pts(di);

        if (f == 0 || p == NULL || di->m_ptcount == 0)
            continue;

        g_polys++;
        Sample s;
        s.c = CPnt3D(0.0f, 0.0f, 0.0f);
        s.ylo = 1e9f;
        s.yhi = -1e9f;
        s.pts = di->m_ptcount;
        s.ditype = di->m_ditype;
        s.camtype = di->m_cameratype;
        s.material = di->m_material;

        for (int i = 0; i < (int)di->m_ptcount; i++)
        {
            CPnt3D w(p[i].x, p[i].y, p[i].z);
            node->TransformToWorld(w);
            s.c.x += w.x; s.c.y += w.y; s.c.z += w.z;

            if (w.y < s.ylo) s.ylo = w.y;
            if (w.y > s.yhi) s.yhi = w.y;
        }

        s.c.x /= (float)s.pts; s.c.y /= (float)s.pts; s.c.z /= (float)s.pts;
        CPnt3D o(0.0f, 0.0f, 0.0f);
        CPnt3D t(di->m_nrm.x, di->m_nrm.y, di->m_nrm.z);
        node->TransformToWorld(o);
        node->TransformToWorld(t);
        s.n = CPnt3D(t.x - o.x, t.y - o.y, t.z - o.z);
        float len = sqrtf(s.n.x * s.n.x + s.n.y * s.n.y + s.n.z * s.n.z);

        if (len > 0.0f) { s.n.x /= len; s.n.y /= len; s.n.z /= len; }

        float dx = s.c.x - g_me.x, dz = s.c.z - g_me.z;
        s.d2 = dx * dx + dz * dz;
        s.name = node->m_name;
        keep(f, s);
    }

    for (zdb::CNodeVector::iterator it = node->m_child.begin(); it != node->m_child.end(); ++it)
        walk(*it, depth + 1);
}
}

extern "C" void __wrap__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal)
{
    __real__ZN10CameraZoom10AttachSealEP10CZSealBody(seal);
    CZSealBody *player = ftsGetPlayer();
    zdb::CWorld *world = zdb::CWorld::m_world;

    if (player == NULL || world == NULL)
        return;

    zdb::CNode *node = player->m_node;
    g_me = CPnt3D(node->m_matrix.m_matrix[3][0], node->m_matrix.m_matrix[3][1], node->m_matrix.m_matrix[3][2]);
    walk(world, 0);
    SOCOM_PORT_TRACE("HOOK: step height %.1f, ground touch %.1f, max slope cos %.2f, jump factor %.2f", theCharacterDynamics.m_stepHeight,
        theCharacterDynamics.m_groundTouchDistance, theCharacterDynamics.m_maxSlopeCos, theCharacterDynamics.m_jumpFactor);
    SOCOM_PORT_TRACE("HOOK: census from %.1f %.1f %.1f: %d nodes, %d DIs, %d flagged polys; flags 0:%d 1:%d 2:%d 3:%d 4:%d 5:%d 6:%d 7:%d",
        g_me.x, g_me.y, g_me.z, g_nodes, g_dis, g_polys, g_count[0], g_count[1], g_count[2], g_count[3], g_count[4],
        g_count[5], g_count[6], g_count[7]);

    for (int f = 1; f < 8; f++)
    {
        for (int i = 0; i < g_nbest[f]; i++)
        {
            const Sample &s = g_best[f][i];
            SOCOM_PORT_TRACE("HOOK: flag %d #%d at %.0f: c %.1f %.1f %.1f n %.2f %.2f %.2f y %.1f..%.1f pts %d di %d cam %d mat %d node %s", f, i,
                sqrtf(s.d2), s.c.x, s.c.y, s.c.z, s.n.x, s.n.y, s.n.z, s.ylo, s.yhi, s.pts, s.ditype, s.camtype, s.material,
                s.name != NULL ? s.name : "-");
        }
    }

#ifdef SOCOM_HOOK_FLAG
    if (g_nbest[SOCOM_HOOK_FLAG] <= SOCOM_HOOK_PICK)
    {
        SOCOM_PORT_TRACE("HOOK: no flag %d poly #%d; the player stays", SOCOM_HOOK_FLAG, SOCOM_HOOK_PICK);
        return;
    }

    const Sample &s = g_best[SOCOM_HOOK_FLAG][SOCOM_HOOK_PICK];
    CPnt3D dir(-s.n.x, 0.0f, -s.n.z);
    float len = sqrtf(dir.x * dir.x + dir.z * dir.z);
    dir.x /= len; dir.z /= len;
    CPnt3D target(s.c.x - dir.x * SOCOM_HOOK_GAP, 0.0f, s.c.z - dir.z * SOCOM_HOOK_GAP);
    CPnt3D probe(target.x, s.yhi + 50.0f, target.z);
    bool was = node->SetActive(false);
    zdb::IntersectStruct *ground = world->GetAltitude(&probe, 100000.0f);
    node->SetActive(was);
    target.y = ground != NULL ? ground->m_pos.y : s.ylo;
    float base = atan2f(dir.x, dir.z);
    float candidates[4] = { base, -base, base + 3.1415927f, -base + 3.1415927f };
    CQuat turn;
    float score = -2.0f;

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

    player->TeleportTo(&target, &turn);
    SOCOM_PORT_TRACE("HOOK: flag %d poly #%d: player to %.1f %.1f %.1f facing %.2f %.2f (match %.2f)", SOCOM_HOOK_FLAG,
        SOCOM_HOOK_PICK, target.x, target.y, target.z, -node->m_matrix.m_matrix[2][0], -node->m_matrix.m_matrix[2][2], score);
#endif
}

#ifdef SOCOM_HOOK_CLIMB
/* Stands in for the HUD's climb action (CZActionBitmap::HudTick selects it, port: unwritten):
 * on the action button's release (X, KEY_RISING; the release is when PreTick calls
 * OnActionButton) with a forward wall hit, do what OnActionButton 0x284834 does for a
 * selected climb (bit 2): ExecuteDelayedAction_Climb and the controller's action flag, so
 * this Tick's CheckDIFwd1 runs ImpactFront. Wraps CZSealBody::DoWallStop (seal.cpp's Tick ->
 * seal_body.cpp) and traces the player's climb / jump frames through GetTerrainMotionFactor. */
#include "gamez/zInput/zinput.h"
extern "C" bool __real__ZN10CZSealBody10DoWallStopEv(CZSealBody *body);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);

extern "C" bool __wrap__ZN10CZSealBody10DoWallStopEv(CZSealBody *body)
{
    CPad *pad = CInput::m_pads[0];

    if (body == ftsGetPlayer() && pad != NULL && pad->m_state[(u8)PAD_BUTTON::PAD_CROSS] == KEY_RISING)
    {
        bool hit = body->m_fwdhit->m_node != NULL;
        SOCOM_PORT_TRACE("HOOK: action released, forward hit %d (app flags %d)%s", (int)hit,
            hit && body->m_fwdhit->m_poly != NULL ? (int)body->m_fwdhit->m_poly->m_appflags : -1, hit ? ": climb action" : "");

        if (hit)
        {
            body->ExecuteDelayedAction_Climb();
            static_cast<CSealCtrl *>(body->m_control)->m_action = 1;
        }
    }

    return __real__ZN10CZSealBody10DoWallStopEv(body);
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer())
    {
        CZBodyAnimBlend *top = body->m_blends->Top();
        int type = top != NULL ? (int)(s16)top->m_animType : -1;
        static int last = -2;
        static int frames = 0;
        bool air = type == 8 || type == 9 || type == 10 || type == 11 || type == (int)(s16)AnimTypes::Jump
            || type == (int)(s16)AnimTypes::ClimbOver || type == (int)(s16)AnimTypes::ClimbMedium || type == 44
            || type == (int)(s16)AnimTypes::StepUp || body->m_airborne;

        if (type != last || (air && (++frames % 4) == 0))
        {
            CPnt3D *p = body->GetPosW();
            SOCOM_PORT_TRACE("HOOK: frame anim %d state %d t %.2f pos %.1f %.1f %.1f alt %.1f air %d descent %.1f fwdhit %d interp %d",
                type, (int)body->m_state, top != NULL ? top->m_tfrac : 0.0f, p->x, p->y, p->z, body->m_alt, (int)body->m_airborne,
                body->m_descent, (int)(body->m_fwdhit->m_node != NULL), (int)body->m_interpolate_animations);
            last = type;
        }
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
#endif
