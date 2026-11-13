/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): node-action boots. Wraps CameraZoom::AttachSeal and
 * CZSealBody::GetTerrainMotionFactor (both called across units, so --wrap sees them).
 * - AttachSeal: lists CNodeAction::m_actions (node, world position, type, valve, range, anims,
 *   icon, text) and the nearest few DI polys of app flags 4 and 5; puts the player in front of
 *   the phase-0 target, facing it.
 * - Each TRIANGLE press (unmapped in the Default controls) moves him to the next target.
 *   Targets (SOCOM_HOOK_TARGETS, /-separated): "f<flag>:<pick>:<gap>" (the pick-th nearest; "t..." among
 *   the wall-like ones at least 15 high)
 *   poly with those app flags) or "n<node>:<gap>" (the biggest wall-like DI poly under that
 *   node, else the node's origin).
 * - Per player frame (GetTerrainMotionFactor): anim changes and every 15th frame the position,
 *   the forward hit's app flags, the action masks / display and the reticule action. */
#include <map>
#include <string>
#include <vector>
#include <list>
#include <unordered_map>
#define protected public /* scratch hook only */
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zNode/node_action.h"
#include "gamez/zGrid/zgrid.h"
#include "gamez/zIntersect/zintersect.h"
#include "gamez/zGame/zgame.h"
#include "gamez/zInput/zinput.h"
#include "gamez/zValve/zvalve.h"
#include <string.h>
#include <stdlib.h>
#include "gamez/zWeapon/zweapon.h"
#include "Apps/FTS/hud/hud.h"
#include "hook_freecam.h"
#include "gamez/zParticle/zparticle.h"

/* test camera on bullet marks (socom-port-fx2): every mark is remembered; 20 frames after the
 * last one of a burst the camera looks at it from SOCOM_HOOK_MARKCAM along its normal for 70
 * frames */
static int g_cam_frame = 0;
static int g_mark_frame = -1000;
static CPnt3D g_mark_pos(0.0f, 0.0f, 0.0f);
static CPnt3D g_mark_norm(0.0f, 1.0f, 0.0f);
static CPnt3D g_glass_centre(0.0f, 0.0f, 0.0f); /* mapglass2: the last placed target's centre */

extern "C" void __real__ZN10CZMarkList10AddNewMarkEPN3zdb15IntersectStructEP12CZProjectilef(CZMarkList *list, zdb::IntersectStruct *hit, CZProjectile *p, float scale);

extern "C" void __wrap__ZN10CZMarkList10AddNewMarkEPN3zdb15IntersectStructEP12CZProjectilef(CZMarkList *list, zdb::IntersectStruct *hit, CZProjectile *p, float scale)
{
    if (hit != NULL && !p->m_lastHitWasPerson)
    {
        g_mark_pos = hit->m_pos;
        g_mark_norm = hit->m_norm;
        g_mark_frame = g_cam_frame;
        SOCOM_PORT_TRACE("HOOK: mark on %s at %.1f %.1f %.1f", hit->m_node != NULL && hit->m_node->m_name != NULL ? hit->m_node->m_name : "-", hit->m_pos.x, hit->m_pos.y, hit->m_pos.z);
    }

    __real__ZN10CZMarkList10AddNewMarkEPN3zdb15IntersectStructEP12CZProjectilef(list, hit, p, scale);
}

static void markcam_tick()
{
    g_cam_frame++;
#ifdef SOCOM_HOOK_MARKCAM
    int age = g_cam_frame - g_mark_frame;

    if (age == 20)
    {
        CPnt3D eye(g_mark_pos.x + g_mark_norm.x * SOCOM_HOOK_MARKCAM, g_mark_pos.y + g_mark_norm.y * SOCOM_HOOK_MARKCAM + 2.0f,
            g_mark_pos.z + g_mark_norm.z * SOCOM_HOOK_MARKCAM);
        freecam_look(eye, g_mark_pos);
        SOCOM_PORT_TRACE("HOOK: test camera on the mark at %.1f %.1f %.1f (normal %.2f %.2f %.2f)", g_mark_pos.x, g_mark_pos.y, g_mark_pos.z,
            g_mark_norm.x, g_mark_norm.y, g_mark_norm.z);
    }
    else if (age == 240)
    {
        freecam_off();
    }
#endif
}

#ifndef SOCOM_HOOK_TARGETS
#define SOCOM_HOOK_TARGETS "f4:0:100"
#endif

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);

namespace
{
struct DIPeek : zdb::CDI
{
    static CPnt4D *pts(zdb::CDI *d) { return static_cast<DIPeek *>(d)->m_pts; }
};

const int KEEP = 4;

struct Sample
{
    float d2;
    CPnt3D c;
    CPnt3D n;
    float ylo, yhi;
    float area;
    const char *name;
};

Sample g_best[8][KEEP];
int g_nbest[8];
const int TALL = 16;
Sample g_tall[8][TALL]; /* the nearest wall-like polys at least 15 high */
int g_ntall[8];
CPnt3D g_me;
zdb::CNode *g_target;
CPnt3D g_saved_pos; /* phase 0's stand point: target "b" goes back to it */
CQuat g_saved_turn;
int g_phase = -1;

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

bool sample(zdb::CNode *node, zdb::CDI *di, Sample &s)
{
    CPnt4D *p = DIPeek::pts(di);

    if (p == NULL || di->m_ptcount == 0)
        return false;

    int pts = di->m_ptcount;
    s.c = CPnt3D(0.0f, 0.0f, 0.0f);
    s.ylo = 1e9f;
    s.yhi = -1e9f;
    float xlo = 1e9f, xhi = -1e9f, zlo = 1e9f, zhi = -1e9f;

    for (int i = 0; i < pts; i++)
    {
        CPnt3D w(p[i].x, p[i].y, p[i].z);
        node->TransformToWorld(w);
        s.c.x += w.x; s.c.y += w.y; s.c.z += w.z;
        if (w.y < s.ylo) s.ylo = w.y;
        if (w.y > s.yhi) s.yhi = w.y;
        if (w.x < xlo) xlo = w.x;
        if (w.x > xhi) xhi = w.x;
        if (w.z < zlo) zlo = w.z;
        if (w.z > zhi) zhi = w.z;
    }

    s.c.x /= (float)pts; s.c.y /= (float)pts; s.c.z /= (float)pts;
    CPnt3D o(0.0f, 0.0f, 0.0f);
    CPnt3D t(di->m_nrm.x, di->m_nrm.y, di->m_nrm.z);
    node->TransformToWorld(o);
    node->TransformToWorld(t);
    s.n = CPnt3D(t.x - o.x, t.y - o.y, t.z - o.z);
    float len = sqrtf(s.n.x * s.n.x + s.n.y * s.n.y + s.n.z * s.n.z);

    if (len > 0.0f) { s.n.x /= len; s.n.y /= len; s.n.z /= len; }

    float w = sqrtf((xhi - xlo) * (xhi - xlo) + (zhi - zlo) * (zhi - zlo));
    s.area = w * (s.yhi - s.ylo);
    float dx = s.c.x - g_me.x, dz = s.c.z - g_me.z;
    s.d2 = dx * dx + dz * dz;
    s.name = node->m_name;
    return true;
}

void walk(zdb::CNode *node, int depth)
{
    if (node == NULL || depth > 40)
        return;

    for (zdb::CDIVector::iterator it = node->m_di.begin(); it != node->m_di.end(); ++it)
    {
        zdb::CDI *di = *it;

        if (di == NULL)
            continue;

        int f = di->m_appflags;
        Sample s;

        if (f != 0 && sample(node, di, s))
        {
            keep(f, s);

            if (s.yhi - s.ylo >= 15.0f && fabsf(s.n.y) < 0.5f)
            {
                int n = g_ntall[f];
                int i = n < TALL ? n : TALL - 1;

                if (n < TALL || s.d2 < g_tall[f][TALL - 1].d2)
                {
                    while (i > 0 && g_tall[f][i - 1].d2 > s.d2)
                    {
                        g_tall[f][i] = g_tall[f][i - 1];
                        i--;
                    }

                    g_tall[f][i] = s;

                    if (n < TALL)
                        g_ntall[f]++;
                }
            }
        }
    }

    for (zdb::CNodeVector::iterator it = node->m_child.begin(); it != node->m_child.end(); ++it)
        walk(*it, depth + 1);
}

/* the biggest wall-like (|n.y| < 0.4) DI poly under the node */
void biggest(zdb::CNode *node, Sample &best, int depth)
{
    if (node == NULL || depth > 20)
        return;

    for (zdb::CDIVector::iterator it = node->m_di.begin(); it != node->m_di.end(); ++it)
    {
        Sample s;

        if (*it != NULL && sample(node, *it, s) && fabsf(s.n.y) < 0.4f && s.area > best.area)
            best = s;
    }

    for (zdb::CNodeVector::iterator it = node->m_child.begin(); it != node->m_child.end(); ++it)
        biggest(*it, best, depth + 1);
}

CPnt3D world_pos(zdb::CNode *node)
{
    CMatrix m;
    sceVu0UnitMatrix(m.m_matrix);
    node->BuildMTW(m);
    return CPnt3D(m.m_matrix[3][0], m.m_matrix[3][1], m.m_matrix[3][2]);
}

void dump(zdb::CNode *node, int depth)
{
    if (node == NULL || depth > 3)
        return;

    zdb::CDI *d0 = node->m_di.size() > 0 ? node->m_di[0] : NULL;
    SOCOM_PORT_TRACE("HOOK: %*snode %s active %d hasDI %d parentbbox %d bbox %.1f %.1f %.1f .. %.1f %.1f %.1f dis %d (type %d cam %d app %d) kids %d",
        depth * 2, "", node->m_name != NULL ? node->m_name : "-", (int)node->m_active, (int)node->m_hasDI, (int)node->m_use_parent_bbox,
        node->m_bbox.m_min.x, node->m_bbox.m_min.y, node->m_bbox.m_min.z, node->m_bbox.m_max.x, node->m_bbox.m_max.y, node->m_bbox.m_max.z,
        (int)node->m_di.size(), d0 != NULL ? (int)d0->m_ditype : -1, d0 != NULL ? (int)d0->m_cameratype : -1, d0 != NULL ? (int)d0->m_appflags : -1,
        (int)node->m_child.size());

    for (zdb::CNodeVector::iterator it = node->m_child.begin(); it != node->m_child.end(); ++it)
        dump(*it, depth + 1);
}

void place(CZSealBody *player, const Sample &s, float gap, const char *what)
{
    g_glass_centre = s.c;
    zdb::CWorld *world = zdb::CWorld::m_world;
    zdb::CNode *node = player->m_node;
    CPnt3D dir(-s.n.x, 0.0f, -s.n.z);
    float len = sqrtf(dir.x * dir.x + dir.z * dir.z);

    if (len < 0.01f) { dir = CPnt3D(0.0f, 0.0f, 1.0f); len = 1.0f; }

    dir.x /= len; dir.z /= len;
    CPnt3D target(s.c.x - dir.x * gap, 0.0f, s.c.z - dir.z * gap);
    CPnt3D probe(target.x, s.ylo + 30.0f, target.z);
    bool was = node->SetActive(false);
    float keep_alt = player->m_alt;
    player->m_alt = probe.y;
    zdb::IntersectStruct *ground = player->SealGetAltitude(&probe, 1.0f);
    player->m_alt = keep_alt;
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

    if (g_phase == 0)
    {
        g_saved_pos = target;
        g_saved_turn = turn;
    }

    player->TeleportTo(&target, &turn);
    /* a standing seal keeps its last altitude hit (m_get_new_altitude is cleared every still
     * frame): refresh it here, or the seal snaps back to the height of the place it left */
    {
        CPnt3D at = target;
        at.y += 11.0f;
        player->m_alt = at.y;
        zdb::IntersectStruct *g = player->SealGetAltitude(&at, 1.0f);

        if (g != NULL)
        {
            player->m_last_altitude.m_pos = g->m_pos;
            player->m_last_altitude.m_norm = g->m_norm;
            player->m_last_altitude.m_poly = g->m_poly;
            player->m_last_altitude.m_node = g->m_node;
            player->m_alt = g->m_pos.y;
        }

        SOCOM_PORT_TRACE("HOOK: altitude at target %.1f (probe ground %.1f)", g != NULL ? g->m_pos.y : -1.0f, target.y);
    }
    SOCOM_PORT_TRACE("HOOK: phase %d %s (%s, c %.1f %.1f %.1f n %.2f %.2f, y %.1f..%.1f): player to %.1f %.1f %.1f facing %.2f %.2f",
        g_phase, what, s.name != NULL ? s.name : "-", s.c.x, s.c.y, s.c.z, s.n.x, s.n.z, s.ylo, s.yhi, target.x, target.y, target.z,
        -node->m_matrix.m_matrix[2][0], -node->m_matrix.m_matrix[2][2]);
}

void go_phase(CZSealBody *player, int phase)
{
    static char buf[256];
    strncpy(buf, SOCOM_HOOK_TARGETS, sizeof(buf) - 1);
    char *tok = strtok(buf, "/");

    for (int i = 0; tok != NULL && i < phase; i++)
        tok = strtok(NULL, "/");

    g_phase = phase;

    if (tok == NULL)
    {
        SOCOM_PORT_TRACE("HOOK: phase %d: no target", phase);
        return;
    }

    if (tok[0] == 'b')
    {
        player->TeleportTo(&g_saved_pos, &g_saved_turn);
        CPnt3D at = g_saved_pos;
        at.y += 11.0f;
        player->m_alt = at.y;
        zdb::IntersectStruct *g = player->SealGetAltitude(&at, 1.0f);

        if (g != NULL)
        {
            player->m_last_altitude.m_pos = g->m_pos;
            player->m_last_altitude.m_norm = g->m_norm;
            player->m_last_altitude.m_poly = g->m_poly;
            player->m_last_altitude.m_node = g->m_node;
            player->m_alt = g->m_pos.y;
        }

        SOCOM_PORT_TRACE("HOOK: phase %d back to %.1f %.1f %.1f", phase, g_saved_pos.x, g_saved_pos.y, g_saved_pos.z);
        return;
    }

    if (tok[0] == 't')
    {
        int flag = 0, pick = 0;
        float gap = 100.0f;
        sscanf(tok + 1, "%d:%d:%f", &flag, &pick, &gap);

        if (flag < 0 || flag > 7 || g_ntall[flag] <= pick)
        {
            SOCOM_PORT_TRACE("HOOK: phase %d: no tall flag %d poly #%d", phase, flag, pick);
            return;
        }

        place(player, g_tall[flag][pick], gap, tok);
        return;
    }

    if (tok[0] == 'f')
    {
        int flag = 0, pick = 0;
        float gap = 100.0f;
        sscanf(tok + 1, "%d:%d:%f", &flag, &pick, &gap);

        if (flag < 0 || flag > 7 || g_nbest[flag] <= pick)
        {
            SOCOM_PORT_TRACE("HOOK: phase %d: no flag %d poly #%d", phase, flag, pick);
            return;
        }

        place(player, g_best[flag][pick], gap, tok);
        return;
    }

    char name[64];
    float gap = 20.0f;
    const char *colon = strchr(tok + 1, ':');
    int n = colon != NULL ? (int)(colon - (tok + 1)) : (int)strlen(tok + 1);
    memcpy(name, tok + 1, n);
    name[n] = 0;

    if (colon != NULL)
        gap = (float)atof(colon + 1);

    zdb::CNode *target = zdb::CWorld::m_world->FindChild(name, true);

    if (target == NULL)
    {
        SOCOM_PORT_TRACE("HOOK: phase %d: no node %s", phase, name);
        return;
    }

    for (zdb::CNode *up = target->m_parent; up != NULL; up = up->m_parent)
        SOCOM_PORT_TRACE("HOOK: ancestor %s active %d hasDI %d parentbbox %d", up->m_name != NULL ? up->m_name : "-", (int)up->m_active,
            (int)up->m_hasDI, (int)up->m_use_parent_bbox);

    dump(target, 0);
    for (zdb::CNode *up = target; up != NULL; up = up->m_parent)
        SOCOM_PORT_TRACE("HOOK: matrix %s: x %.2f %.2f %.2f y %.2f %.2f %.2f z %.2f %.2f %.2f t %.1f %.1f %.1f", up->m_name != NULL ? up->m_name : "-",
            up->m_matrix.m_matrix[0][0], up->m_matrix.m_matrix[0][1], up->m_matrix.m_matrix[0][2], up->m_matrix.m_matrix[1][0], up->m_matrix.m_matrix[1][1],
            up->m_matrix.m_matrix[1][2], up->m_matrix.m_matrix[2][0], up->m_matrix.m_matrix[2][1], up->m_matrix.m_matrix[2][2], up->m_matrix.m_matrix[3][0],
            up->m_matrix.m_matrix[3][1], up->m_matrix.m_matrix[3][2]);
    g_target = target;
    Sample best;
    best.area = 0.0f;
    biggest(target, best, 0);

    if (best.area <= 0.0f)
    {
        best.c = world_pos(target);
        best.n = CPnt3D(1.0f, 0.0f, 0.0f);
        best.ylo = best.yhi = best.c.y;
        best.name = target->m_name;
    }

    /* approach side: the poly normal, its reverse, then the compass: the first stand point whose
     * eye-height ray to the poly centre meets the target's action node first */
    CNodeAction *want = CNodeAction::GetAction(target, true);
    CPnt3D n0(best.n.x, 0.0f, best.n.z);
    float l0 = sqrtf(n0.x * n0.x + n0.z * n0.z);

    if (l0 < 0.01f) { n0 = CPnt3D(1.0f, 0.0f, 0.0f); l0 = 1.0f; }

    n0.x /= l0; n0.z /= l0;
    float a0 = atan2f(n0.z, n0.x);
    static const float steps[10] = { 0.0f, 3.1415927f, 0.7853982f, -0.7853982f, 1.5707963f, -1.5707963f, 2.3561945f, -2.3561945f, 0.3926991f, -0.3926991f };
    zdb::CNode *pnode = player->m_node;

    for (int k = 0; k < 10 && want != NULL; k++)
    {
        float a = a0 + steps[k];
        CPnt3D dir(cosf(a), 0.0f, sinf(a));
        CPnt3D stand(best.c.x + dir.x * gap, best.c.y + 6.0f, best.c.z + dir.z * gap);
        bool was = pnode->SetActive(false);
        float keep_alt = player->m_alt;
        player->m_alt = stand.y; /* SealProcessAltitude drops ground far above the current altitude */
        zdb::IntersectStruct *ground = player->SealGetAltitude(&stand, 1.0f);
        player->m_alt = keep_alt;
        float gy = ground != NULL ? ground->m_pos.y : -99999.0f;
        CPnt3D eye(stand.x, gy + 24.0f, stand.z);
        CPnt3D end(best.c.x + (best.c.x - eye.x) * 0.3f, best.c.y + (best.c.y - eye.y) * 0.3f, best.c.z + (best.c.z - eye.z) * 0.3f);
        zdb::DiIntersect *hits = ground != NULL ? zdb::CWorld::m_world->GetIntersects(&eye, &end) : NULL;
        pnode->SetActive(was);
        zdb::IntersectStruct *first = NULL;
        float fd = 1e18f;

        for (int i = 0; hits != NULL && i < hits->m_Cnt; i++)
        {
            zdb::IntersectStruct *h = &hits->m_Intersects[i];
            CPnt3D d;
            h->m_pos.Sub(&eye, &d);
            float dd = d.x * d.x + d.y * d.y + d.z * d.z;

            if (dd < fd) { fd = dd; first = h; }
        }

        CNodeAction *got = first != NULL ? CNodeAction::GetAction(first->m_node, true) : NULL;
        SOCOM_PORT_TRACE("HOOK: try %d dir %.2f %.2f ground %.1f first %s at %.1f -> %s", k, dir.x, dir.z, gy,
            first != NULL && first->m_node != NULL && first->m_node->m_name != NULL ? first->m_node->m_name : "-", first != NULL ? sqrtf(fd) : -1.0f,
            got == want ? "ok" : "no");

        if (got == want && gy > best.c.y - 40.0f)
        {
            best.n = dir;
            best.ylo = gy - 24.0f; /* place() probes from ylo + 30 */
            break;
        }
    }

    place(player, best, gap, tok);
}
}

extern "C" void __wrap__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal)
{
    __real__ZN10CameraZoom10AttachSealEP10CZSealBody(seal);
    CZSealBody *player = ftsGetPlayer();
    zdb::CWorld *world = zdb::CWorld::m_world;

    if (player == NULL || world == NULL || g_phase >= 0)
        return;

    zdb::CNode *node = player->m_node;
    g_me = CPnt3D(node->m_matrix.m_matrix[3][0], node->m_matrix.m_matrix[3][1], node->m_matrix.m_matrix[3][2]);
    walk(world, 0);

    for (CNodeAction::Container::iterator it = CNodeAction::m_actions.begin(); it != CNodeAction::m_actions.end(); ++it)
    {
        CNodeAction *a = *it;
        CPnt3D p = a->m_node != NULL ? world_pos(a->m_node) : CPnt3D(0.0f, 0.0f, 0.0f);
        SOCOM_PORT_TRACE("HOOK: action %d node %s at %.1f %.1f %.1f type %d valve %s=%d range %.0f anims %d icon %p (tex %p) text %s",
            (int)a->m_id, a->m_node != NULL ? a->m_node->m_name : "-", p.x, p.y, p.z, (int)a->m_type,
            a->m_valve != NULL && a->m_valve->m_name != NULL ? a->m_valve->m_name : "-", a->m_valve != NULL ? (int)a->m_valve->m_value : -1,
            a->m_range, (int)a->m_anim.size(), a->m_pTexHandle, a->m_pTexHandle != NULL ? a->m_pTexHandle->m_texture : NULL,
            a->m_descriptor != NULL ? a->m_descriptor : "-");
    }

    for (int f = 4; f < 6; f++)
    {
        for (int i = 0; i < g_nbest[f]; i++)
        {
            const Sample &s = g_best[f][i];
            SOCOM_PORT_TRACE("HOOK: flag %d #%d at %.0f: c %.1f %.1f %.1f n %.2f %.2f %.2f y %.1f..%.1f node %s", f, i,
                sqrtf(s.d2), s.c.x, s.c.y, s.c.z, s.n.x, s.n.y, s.n.z, s.ylo, s.yhi, s.name != NULL ? s.name : "-");
        }
    }

    for (int f = 4; f < 6; f++)
    {
        for (int i = 0; i < g_ntall[f]; i++)
        {
            const Sample &s = g_tall[f][i];
            SOCOM_PORT_TRACE("HOOK: tall flag %d #%d at %.0f: c %.1f %.1f %.1f n %.2f %.2f %.2f y %.1f..%.1f node %s", f, i,
                sqrtf(s.d2), s.c.x, s.c.y, s.c.z, s.n.x, s.n.y, s.n.z, s.ylo, s.yhi, s.name != NULL ? s.name : "-");
        }
    }

    go_phase(player, 0);
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer())
    {
        CPad *pad = CInput::m_pads[0];

        if (pad != NULL && pad->m_state[(u8)PAD_BUTTON::PAD_TRIANGLE] == KEY_FALLING && g_phase >= 0)
            go_phase(body, g_phase + 1);

        CZBodyAnimBlend *top = body->m_blends->Top();
        int type = top != NULL ? (int)(s16)top->m_animType : -1;
        static int last = -2;
        static int frames = 0;
        static unsigned last_mask = 0xffffffff;
        unsigned mask = body->m_action_available_mask;

        if (type != last || mask != last_mask || (++frames % 15) == 0)
        {
            CPnt3D *p = body->GetPosW();
            zdb::CHit *hit = body->m_fwdhit;
            int flags = hit->m_node != NULL && hit->m_poly != NULL ? (int)hit->m_poly->m_appflags : -1;
            zdb::CNode *ra = body->m_last_reticule_action.m_node;
            zdb::CNode *rs = body->m_last_reticule.m_node;
            CSealCtrl *sc = static_cast<CSealCtrl *>(body->m_control);
            CNodeAction *na = body->GetReticuleAction(false);
            SOCOM_PORT_TRACE("HOOK: frame anim %d state %d pos %.1f %.1f %.1f fwd %d%s%s avail 0x%x sel 0x%x disp %d act %d ret %s/%s goal %d%d valve %d face %.2f %.2f tgt x %.2f %.2f z %.2f %.2f",
                type, (int)body->m_state, p->x, p->y, p->z, flags, hit->m_node != NULL ? " " : "",
                hit->m_node != NULL && hit->m_node->m_name != NULL ? hit->m_node->m_name : "", mask, body->m_action_selection_mask,
                (int)body->m_action_display_on, (int)static_cast<CSealCtrl *>(body->m_control)->m_action,
                ra != NULL && ra->m_name != NULL ? ra->m_name : "-", rs != NULL && rs->m_name != NULL ? rs->m_name : "-",
                (int)sc->m_goal_pos_valid, (int)sc->m_goal_dir_valid, na != NULL && na->m_valve != NULL ? (int)na->m_valve->m_value : -1,
                -body->m_node->m_matrix.m_matrix[2][0], -body->m_node->m_matrix.m_matrix[2][2],
                g_target != NULL ? g_target->m_matrix.m_matrix[0][0] : 0.0f, g_target != NULL ? g_target->m_matrix.m_matrix[0][2] : 0.0f,
                g_target != NULL ? g_target->m_matrix.m_matrix[2][0] : 0.0f, g_target != NULL ? g_target->m_matrix.m_matrix[2][2] : 0.0f);
            last = type;
            last_mask = mask;
        }
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}

/* reticle diagnostic (node phases): every 20th CheckDIShoot re-runs its ray and lists the hits */
extern "C" void __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat);

extern "C" void __wrap__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat)
{
    __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(body, eye, mat);

    if (body == ftsGetPlayer())
    {
        markcam_tick();
        freecam_apply();

        /* fire diagnostic (mapglass2): R1 presses with the input / menu / weapon-tick state, and every
         * change of the current ammo count */
        static int last_ammo = -999;
        static int r1_frames = 0;
        CPad *pad = CInput::m_pads[0];
        CSealCtrl *sc = static_cast<CSealCtrl *>(body->m_control);
        int ammo = body->m_kit.GetCurAmmoCount();
        bool r1 = pad != NULL && pad->m_state[(u8)PAD_BUTTON::PAD_TRIGGER_R1] == KEY_FALLING;

        if (r1 || ammo != last_ammo)
            SOCOM_PORT_TRACE("HOOK: fire %s ammo %d input %d menu %d weptick-off %d cam %d alive %d", r1 ? "R1" : "-", ammo,
                sc != NULL ? (int)sc->m_input_enabled : -1, sc != NULL ? (int)sc->GetMenuState() : -1, (int)CZWeapon::m_weaponTickDisabled,
                theHUD != NULL ? (int)theHUD->m_missioncams.IsPlaying() : -1, (int)body->m_isAlive);

#ifdef SOCOM_HOOK_GLASSCAM
        /* glass test camera (mapglass2): from the first shot after the mission cameras, look at the
         * phase target's window from SOCOM_HOOK_GLASSCAM ("dx,dy,dz" offset from its centre) for
         * 150 frames */
        static int glass_frames = -1;

        if (glass_frames < 0 && last_ammo != -999 && ammo < last_ammo && g_target != NULL)
        {
            static const float off[3] = { SOCOM_HOOK_GLASSCAM };
            CPnt3D c = g_glass_centre;
            freecam_look(CPnt3D(c.x + off[0], c.y + off[1], c.z + off[2]), c);
            glass_frames = 0;
            SOCOM_PORT_TRACE("HOOK: glass camera on %.1f %.1f %.1f", c.x, c.y, c.z);
        }
        else if (glass_frames >= 0 && ++glass_frames == 150)
        {
            freecam_off();
            SOCOM_PORT_TRACE("HOOK: glass camera off");
        }
#endif
        (void)r1_frames;
        last_ammo = ammo;
    }

    static int calls = 0;

    if (body != ftsGetPlayer() || g_phase < 0 || (++calls % 90) != 0)
        return;

    f32 reach = zdb::CWorld::m_world->m_camera->m_mid_plane;

    if (reach > 600.0f)
        reach = 600.0f;

    CPnt3D local(0.0f, 0.0f, -reach);
    CPnt3D end;
    mat->Transform(&local, &end, 1);
    zdb::SetCameraCollideFlagRequired(true);
    zdb::CNode *node = body->GetNode();
    bool active = node->SetActive(false);
    zdb::DiIntersect *hits = zdb::CWorld::m_world->GetIntersects(eye, &end);
    node->SetActive(active);
    zdb::SetCameraCollideFlagRequired(false);
    SOCOM_PORT_TRACE("HOOK: ray %.1f %.1f %.1f -> %.1f %.1f %.1f: %d hits", eye->x, eye->y, eye->z, end.x, end.y, end.z, hits != NULL ? hits->m_Cnt : -1);

    for (int i = 0; hits != NULL && i < hits->m_Cnt && i < 12; i++)
    {
        zdb::IntersectStruct *h = &hits->m_Intersects[i];
        CPnt3D d;
        h->m_pos.Sub(eye, &d);
        u32 material = h->GetMaterial();
        CMaterialEx *ex = material < CMaterialExArray::m_materialex_list.size() ? CMaterialExArray::m_materialex_list[material] : NULL;
        CNodeAction *a = CNodeAction::GetAction(h->m_node, true);
        zdb::CNode *p = h->m_node != NULL ? h->m_node->m_parent : NULL;
        SOCOM_PORT_TRACE("HOOK:  hit %d %s (parent %s) dist %.1f mat %u pen %.2f vol %d liq %d pick %d cam %d action %s", i,
            h->m_node != NULL && h->m_node->m_name != NULL ? h->m_node->m_name : "-", p != NULL && p->m_name != NULL ? p->m_name : "-",
            sqrtf(d.x * d.x + d.y * d.y + d.z * d.z), material, ex != NULL ? ex->m_penetration : -1.0f, ex != NULL ? (int)ex->m_volumetric : -1,
            ex != NULL ? (int)ex->m_liquid : -1, ex != NULL ? (int)ex->m_pickup : -1, h->m_poly != NULL ? (int)h->m_poly->m_cameratype : -1,
            a != NULL && a->m_node != NULL ? a->m_node->m_name : "-");
    }
}

#ifdef SOCOM_HOOK_SHARDLIFE
/* shard life stretch for screenshots (mapglass2, test only): link with
 * EXTRAWRAP=-Wl,--wrap=_ZN8Particle20Destruction_Instance6CreateERK6CPnt4DS3_RK6CPnt3DfffPN3zdb7CVisualES4_PNS_5PropsE */
extern "C" void __real__ZN8Particle20Destruction_Instance6CreateERK6CPnt4DS3_RK6CPnt3DfffPN3zdb7CVisualES4_PNS_5PropsE(const CPnt4D &, const CPnt4D &, const CPnt3D &, float, float, float, zdb::CVisual *, CPnt3D, Particle::Props *);
extern "C" void __wrap__ZN8Particle20Destruction_Instance6CreateERK6CPnt4DS3_RK6CPnt3DfffPN3zdb7CVisualES4_PNS_5PropsE(const CPnt4D &pos, const CPnt4D &vel, const CPnt3D &spin, float radius, float life, float opacity, zdb::CVisual *visual, CPnt3D scale, Particle::Props *props)
{
    CPnt4D slow(vel.x * 0.35f, vel.y * 0.35f, vel.z * 0.35f, 0.0f);
    props->m_accelW.y = -98.0f * 0.1f; /* the shared Props: test only */
    __real__ZN8Particle20Destruction_Instance6CreateERK6CPnt4DS3_RK6CPnt3DfffPN3zdb7CVisualES4_PNS_5PropsE(pos, slow, spin, radius, life * SOCOM_HOOK_SHARDLIFE, opacity, visual, scale, props);
}
#endif