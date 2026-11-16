/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-mod-sp, the last single-player gaps in m8. Linked with
 * ../state/hook_state.cpp (menus, intro movie, briefing cameras, heap trace). It traces:
 *  - CAMERA_PARAMS: the command's begin / tick (ZAnim.AddCmd's entry is replaced by tracing
 *    wrappers around the real functions) and every change of the world camera's fields of view,
 *    planes, fog range / altitude / switches and range scale after CCamera::Update, with the
 *    mission camera that plays.
 *  - the AI map set at the first player frame (maps, the set graph's nodes) and every cross-map
 *    RegisterPathPlan; at frame SP_ROUTE_AT (default 600) an awake enemy off map SP_ROUTE_MAP
 *    (default 2, Dredge2) gets a route to a walkable cell by that map's graph node (SetRoute; its
 *    script paused), traced every 60 frames and at each map change for SP_ROUTE_LEN frames, the
 *    test camera following it; -DSP_ROUTE_PLACE=<cells> first puts it that far from the map-0 graph
 *    node nearest to the goal; -DSP_NOROUTE leaves the test out;
 *  - every muzzle-flash light map (CWorld::AddLightMap) and the heap every 600 frames;
 *    -DSP_SLOWMO=<n>: from flash n the scheduled tasks run at 1/50 speed for SP_SLOWLEN frames
 *    (default 900) with the test camera on the player, so a flash's light can be photographed;
 *  - -DSP_GOPT=<flag> turns one of CHUD::StatusLine's debug readouts on (gopt.doStatusLine,
 *    doStatusLineSmall, doAssetReport, doTaskReport, doRenderReport, doFPS); -DSP_VISINFO also
 *    sets ai::visinfo.
 * Switches: -DSP_NOPARAMS (the CAMERA_PARAMS begin does nothing and the tick returns true at once:
 * the port before the command was written, the "before"). With ../state/hook_state.cpp's
 * -DSOCOM_HOOK_CAMS_PLAY the briefing cameras play in full. pad_fire.txt fires once a second from
 * pad read 1530 for 60 s. */
#include <list>
#include <vector>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zNode/znode.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zCamera/zcam.h"
#include "gamez/zAnim/zanim.h"
#include "gamez/zVideo/zvid.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zGame/zgame.h"
#include "Apps/FTS/hud/hud.h"
#include <stdio.h>
#include <string.h>
#include <malloc.h>
#include "hook_clock.h"

namespace
{
void (*g_params_begin)(_zanim_cmd_hdr *);
bool (*g_params_tick)(_zanim_cmd_hdr *, f32 *);
unsigned g_params_ticks;
unsigned g_updates;

const char *cam_name()
{
    if (theHUD == NULL || !theHUD->m_missioncams.IsPlaying())
        return "-";

    return theHUD->m_missioncams.m_currentcam != NULL ? theHUD->m_missioncams.m_currentcam->m_identifier : "?";
}

void params_begin(_zanim_cmd_hdr *header)
{
    const u8 *b = reinterpret_cast<const u8 *>(header);
    SOCOM_PORT_TRACE("HOOK SP: CAMERA_PARAMS begin flags %02x size %u (cam %s)%s", b[4], (unsigned)header->data_size, cam_name(),
#ifdef SP_NOPARAMS
                     " - skipped (SP_NOPARAMS)");
#else
                     "");
    g_params_begin(header);
#endif
}

bool params_tick(_zanim_cmd_hdr *header, f32 *dT)
{
#ifdef SP_NOPARAMS
    return true;
#else
    f32 before = *dT;
    bool done = g_params_tick(header, dT);

    if (g_params_ticks++ < 40 || done)
        SOCOM_PORT_TRACE("HOOK SP: CAMERA_PARAMS tick flags %02x dT %.4f -> %.4f done %d (cam %s)", reinterpret_cast<const u8 *>(header)[4],
                         before, *dT, (int)done, cam_name());

    return done;
#endif
}

struct Snap
{
    float hfov, vfov, nearp, midp, farp, fnear, ffar, ftop, fbottom, range;
    int fog, alt;
};

Snap g_last;
bool g_have;
}

extern "C" u16 __real__ZN10CZAnimMain6AddCmdEPKcPFP14_zanim_cmd_hdrP5_zrdrEPFvS3_EPFbS3_PfES9_(
    CZAnimMain *main, const char *name, _zanim_cmd_hdr *(*parser)(_zrdr *), void (*begin)(_zanim_cmd_hdr *),
    bool (*tick)(_zanim_cmd_hdr *, f32 *), void (*end)(_zanim_cmd_hdr *));
extern "C" u16 __wrap__ZN10CZAnimMain6AddCmdEPKcPFP14_zanim_cmd_hdrP5_zrdrEPFvS3_EPFbS3_PfES9_(
    CZAnimMain *main, const char *name, _zanim_cmd_hdr *(*parser)(_zrdr *), void (*begin)(_zanim_cmd_hdr *),
    bool (*tick)(_zanim_cmd_hdr *, f32 *), void (*end)(_zanim_cmd_hdr *))
{
    if (name != NULL && strcmp(name, "CAMERA_PARAMS") == 0)
    {
        g_params_begin = begin;
        g_params_tick = tick;
        begin = params_begin;
        tick = params_tick;
        SOCOM_PORT_TRACE("HOOK SP: CAMERA_PARAMS registered (begin %p tick %p)", (void *)g_params_begin, (void *)g_params_tick);
    }

    return __real__ZN10CZAnimMain6AddCmdEPKcPFP14_zanim_cmd_hdrP5_zrdrEPFvS3_EPFbS3_PfES9_(main, name, parser, begin, tick, end);
}

extern "C" void __real__ZN3zdb7CCamera6UpdateENS_13tag_ZCAM_TYPEE(zdb::CCamera *camera, zdb::tag_ZCAM_TYPE type);
extern "C" void __wrap__ZN3zdb7CCamera6UpdateENS_13tag_ZCAM_TYPEE(zdb::CCamera *camera, zdb::tag_ZCAM_TYPE type)
{
    __real__ZN3zdb7CCamera6UpdateENS_13tag_ZCAM_TYPEE(camera, type);

    if (zdb::CWorld::m_world == NULL || zdb::CWorld::m_world->m_camera != camera)
        return;

    g_updates++;
    Snap s;
    s.hfov = camera->m_hfov * 2.0f * 57.29578f;
    s.vfov = camera->m_vfov * 2.0f * 57.29578f;
    s.nearp = camera->m_near_plane;
    s.midp = camera->m_mid_plane;
    s.farp = camera->m_far_plane;
    s.fnear = camera->m_fog_near;
    s.ffar = camera->m_fog_far;
    s.ftop = camera->m_fog_top;
    s.fbottom = camera->m_fog_bottom;
    s.range = camera->m_RangeScale;
    s.fog = camera->m_fog_enabled;
    s.alt = camera->m_fog_alt_enabled;

    /* in play the far / mid plane and fog range follow the view every frame (SeeFarther): those
       are traced every 600 updates, the rest at each change */
    bool cam = theHUD != NULL && theHUD->m_missioncams.IsPlaying();
    bool changed = !g_have || s.hfov != g_last.hfov || s.vfov != g_last.vfov || s.nearp != g_last.nearp || s.ftop != g_last.ftop ||
                   s.fbottom != g_last.fbottom || s.range != g_last.range || s.fog != g_last.fog || s.alt != g_last.alt;

    if (cam && memcmp(&s, &g_last, sizeof(s)) != 0)
        changed = true;

    if (!cam && g_updates % 600 == 0 && memcmp(&s, &g_last, sizeof(s)) != 0)
        changed = true;

    if (changed)
    {
        SOCOM_PORT_TRACE("HOOK SP: camera (update %u, cam %s) fov %.1f x %.1f deg, near %.2f mid %.1f far %.1f, fog %d %.1f..%.1f, alt %d %.1f..%.1f, range scale %.2f",
                         g_updates, cam_name(), s.hfov, s.vfov, s.nearp, s.midp, s.farp, s.fog, s.fnear, s.ffar, s.alt, s.fbottom, s.ftop,
                         s.range);
        g_last = s;
        g_have = true;
    }
}

/* ---- cross-map AI routes ------------------------------------------------------------------ */
#include "gamez/zAI/zai.h"
#include "gamez/zGraph/graph_graph.h"
#include <math.h>
#include "hook_freecam.h"

#ifndef SP_ROUTE_AT
#define SP_ROUTE_AT 600 /* player frames (CheckDIShoot) into the mission */
#endif
#ifndef SP_ROUTE_LEN
#define SP_ROUTE_LEN 2400
#endif
#ifndef SP_ROUTE_MAP
#define SP_ROUTE_MAP 2 /* the goal's AI map (m8: 1 Dredge1, 2 Dredge2, 3 Lodge) */
#endif

namespace
{
unsigned g_frames;
CZSealBody *g_seals[64];
int g_nseals;
CZSealBody *g_route_ai;
CAiMapLoc g_route_goal;
int g_route_done_shown;

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

CSealCtrlAi *ai_of(CZSealBody *s)
{
    return s != NULL && s->m_control != NULL ? static_cast<CSealCtrl *>(s->m_control)->GetSealCtrlAi() : NULL;
}

bool walkable(const CAiMapLoc &l)
{
    CAiCell *c = AiMaps.GetCell(l);
    return c != NULL && CAiMap::IsWalkable(c) && !c->m_action;
}

void census()
{
    int i = 0;

    for (CAiMaps::iterator it = AiMaps.begin(); it != AiMaps.end(); ++it, ++i)
    {
        CAiMap *m = (CAiMap *)*it;
        SOCOM_PORT_TRACE("HOOK SP: AI map %d id %d '%s' %u x %u cells of %.1f, floor %d, links %d regions %d routes %d graph %d nodes", i,
                         (int)m->m_mapid, m->m_name, m->m_nx, m->m_ny, m->m_dx, (int)m->m_floor, (int)m->m_linksTable.size(),
                         (int)m->m_regionTable.size(), (int)m->m_routeTable.size(), m->m_graph != NULL ? (int)m->m_graph->m_nodes.size() : -1);
    }

    CGraph *g = AiMaps.m_graph;

    if (g == NULL)
    {
        SOCOM_PORT_TRACE("HOOK SP: AI map set: no graph");
        return;
    }

    SOCOM_PORT_TRACE("HOOK SP: AI map set graph: %d nodes %d edges", (int)g->m_nodes.size(), (int)g->m_edges.size());

    for (std::list<CGNode *>::iterator n = g->m_nodes.begin(); n != g->m_nodes.end(); ++n)
    {
        const CAiMapLoc *l = static_cast<const CAiMapLoc *>((*n)->m_nodeEx);
        CPnt3D p(0.0f, 0.0f, 0.0f);

        if (l != NULL)
            AiMaps.GetCellCenter(*l, &p);

        SOCOM_PORT_TRACE("HOOK SP:   node %s (%d:%d,%d) at %.0f %.0f %.0f, %d edges", (*n)->m_name != NULL ? (*n)->m_name : "-",
                         l != NULL ? (int)l->m_mapid : -1, l != NULL ? (int)l->x : -1, l != NULL ? (int)l->y : -1, p.x, p.y, p.z,
                         (int)(*n)->m_edges.size());
    }
}

void trace_route(const char *tag)
{
    CZSealBody *s = g_route_ai;
    CSealCtrlAi *ai = ai_of(s);

    if (ai == NULL)
        return;

    SOCOM_PORT_TRACE("HOOK SP: f%u route %s %s at %.0f %.0f %.0f (%d:%d,%d) alive %d mode %d path %d pts %d legs %d leg %d state %d",
                     g_frames, tag, s->m_node->m_name, s->GetPosW()->x, s->GetPosW()->y, s->GetPosW()->z, (int)s->m_mapLocValid.m_mapid,
                     (int)s->m_mapLocValid.x, (int)s->m_mapLocValid.y, (int)s->m_isAlive, (int)ai->m_mode, (int)ai->m_path.m_state,
                     (int)ai->m_path.m_points.size(), (int)ai->m_path.m_legcount, (int)ai->m_path.m_curleg, (int)ai->GetAiState()->m_state);
}

void dump_path()
{
    CSealCtrlAi *ai = ai_of(g_route_ai);
    int n = (int)ai->m_path.m_points.size();
    int last = -1, run = 0;
    char line[256];
    line[0] = 0;

    /* the points are kept goal first: walk them from the start */
    for (int i = n - 1; i >= 0; i--)
    {
        const CAiMapLoc &l = ai->m_path.m_points[i].m_loc;

        if ((int)l.m_mapid != last)
        {
            if (last >= 0)
                SOCOM_PORT_TRACE("HOOK SP:   path on map %d: %d points, %s", last, run, line);

            last = l.m_mapid;
            run = 0;
            snprintf(line, sizeof(line), "from (%d,%d)", (int)l.x, (int)l.y);
        }

        run++;

        if (i == 0 || (int)ai->m_path.m_points[i - 1].m_loc.m_mapid != last)
        {
            size_t len = strlen(line);
            snprintf(line + len, sizeof(line) - len, " to (%d,%d)", (int)l.x, (int)l.y);
        }
    }

    if (last >= 0)
        SOCOM_PORT_TRACE("HOOK SP:   path on map %d: %d points, %s", last, run, line);
}

void start_route()
{
    CZSealBody *player = ftsGetPlayer();
    zdb::CWorld *world = zdb::CWorld::m_world;
    CGraph *g = AiMaps.m_graph;

    if (player == NULL || world == NULL || g == NULL)
        return;

    g_nseals = 0;
    walk(world, 0);

    /* the goal: a walkable cell near the set-graph node on map SP_ROUTE_MAP */
    const CAiMapLoc *node = NULL;

    for (std::list<CGNode *>::iterator n = g->m_nodes.begin(); n != g->m_nodes.end() && node == NULL; ++n)
    {
        const CAiMapLoc *l = static_cast<const CAiMapLoc *>((*n)->m_nodeEx);

        if (l != NULL && (int)l->m_mapid == SP_ROUTE_MAP)
            node = l;
    }

    if (node == NULL)
    {
        SOCOM_PORT_TRACE("HOOK SP: route: no graph node off map 0");
        return;
    }

    bool found = false;

    for (int r = 2; r <= 8 && !found; r++)
        for (int dy = -r; dy <= r && !found; dy++)
            for (int dx = -r; dx <= r && !found; dx++)
            {
                CAiMapLoc l = *node;
                l.x = node->x + dx;
                l.y = node->y + dy;

                if ((dx == -r || dx == r || dy == -r || dy == r) && walkable(l))
                {
                    g_route_goal = l;
                    found = true;
                }
            }

    if (!found)
    {
        SOCOM_PORT_TRACE("HOOK SP: route: no walkable cell near (%d:%d,%d)", (int)node->m_mapid, (int)node->x, (int)node->y);
        return;
    }

    CPnt3D goal;
    AiMaps.GetCellCenter(g_route_goal, &goal);
    float best = 1e30f;

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];

        if (s == player || (s->m_team & player->m_team) != 0 || !s->m_isAlive || ai_of(s) == NULL || ai_of(s)->m_sleeping)
            continue;

        if (s->m_mapLocValid.m_mapid == g_route_goal.m_mapid)
            continue;

        CPnt3D p = *s->GetPosW();
        float d = (p.x - goal.x) * (p.x - goal.x) + (p.z - goal.z) * (p.z - goal.z);

        if (d < best)
        {
            best = d;
            g_route_ai = s;
        }
    }

    if (g_route_ai == NULL)
    {
        SOCOM_PORT_TRACE("HOOK SP: route: no awake enemy off map %d", (int)g_route_goal.m_mapid);
        return;
    }

    CSealCtrlAi *ai = ai_of(g_route_ai);
    CAiState *st = ai->GetAiState();

    /* the AI's own script would take the route away: pause it for the test */
    if (st->m_state == STATE_SCRIPT && static_cast<CAiSScript *>(st)->m_anim != NULL)
        static_cast<CAiSScript *>(st)->m_anim->Pause();

    g_route_ai->m_invincible = 1;

#ifdef SP_ROUTE_PLACE
    /* -DSP_ROUTE_PLACE: the AI is first put SP_ROUTE_PLACE cells from the map-0 graph node nearest to
       the goal (the ELF's route drops the leg from the start to the first link, see the note) */
    const CAiMapLoc *near0 = NULL;
    float nbest = 1e30f;

    for (std::list<CGNode *>::iterator n = g->m_nodes.begin(); n != g->m_nodes.end(); ++n)
    {
        const CAiMapLoc *l = static_cast<const CAiMapLoc *>((*n)->m_nodeEx);
        CPnt3D p;

        if (l == NULL || l->m_mapid != 0 || AiMaps.GetCellCenter(*l, &p) == NULL)
            continue;

        float d = (p.x - goal.x) * (p.x - goal.x) + (p.z - goal.z) * (p.z - goal.z);

        if (d < nbest)
        {
            nbest = d;
            near0 = l;
        }
    }

    bool placed = false;

    for (int r = SP_ROUTE_PLACE; r <= SP_ROUTE_PLACE + 6 && near0 != NULL && !placed; r++)
        for (int dy = -r; dy <= r && !placed; dy++)
            for (int dx = -r; dx <= r && !placed; dx++)
            {
                CAiMapLoc l = *near0;
                l.x = near0->x + dx;
                l.y = near0->y + dy;
                CPnt3D at;

                if ((dx == -r || dx == r || dy == -r || dy == r) && walkable(l) && AiMaps.GetCellCenter(l, &at) != NULL)
                {
                    CQuat turn;
                    turn.MakeYRot(0.0f);
                    g_route_ai->TeleportTo(&at, &turn);
                    g_route_ai->m_get_new_altitude = 1;
                    placed = true;
                    SOCOM_PORT_TRACE("HOOK SP: f%u route %s put at (%d:%d,%d) %.0f %.0f %.0f, near the link (0:%d,%d)", g_frames,
                                     g_route_ai->m_node->m_name, (int)l.m_mapid, (int)l.x, (int)l.y, at.x, at.y, at.z, (int)near0->x,
                                     (int)near0->y);
                }
            }
#endif

    SOCOM_PORT_TRACE("HOOK SP: f%u route %s chosen for (%d:%d,%d) at %.0f %.0f %.0f", g_frames, g_route_ai->m_node->m_name,
                     (int)g_route_goal.m_mapid, (int)g_route_goal.x, (int)g_route_goal.y, goal.x, goal.y, goal.z);
    freecam_node(g_route_ai->m_node, 50.0f, 60.0f, 70.0f);
}

void set_route()
{
    CSealCtrlAi *ai = ai_of(g_route_ai);
    bool ok = ai->SetRoute(g_route_goal);
    SOCOM_PORT_TRACE("HOOK SP: f%u route %s from (%d:%d,%d) to (%d:%d,%d): SetRoute %d", g_frames, g_route_ai->m_node->m_name,
                     (int)g_route_ai->m_mapLocValid.m_mapid, (int)g_route_ai->m_mapLocValid.x, (int)g_route_ai->m_mapLocValid.y,
                     (int)g_route_goal.m_mapid, (int)g_route_goal.x, (int)g_route_goal.y, (int)ok);
}
}

extern "C" bool __real__ZN7CAiMaps16RegisterPathPlanERK9CAiMapLocS2_P7CAiPath(CAiMaps *maps, const CAiMapLoc &start, const CAiMapLoc &goal, CAiPath *path);
extern "C" bool __wrap__ZN7CAiMaps16RegisterPathPlanERK9CAiMapLocS2_P7CAiPath(CAiMaps *maps, const CAiMapLoc &start, const CAiMapLoc &goal, CAiPath *path)
{
    bool ok = __real__ZN7CAiMaps16RegisterPathPlanERK9CAiMapLocS2_P7CAiPath(maps, start, goal, path);

    if (start.m_mapid != goal.m_mapid)
        SOCOM_PORT_TRACE("HOOK SP: RegisterPathPlan across maps (%d:%d,%d) -> (%d:%d,%d): %d, %d waypoints (%d legs)", (int)start.m_mapid,
                         (int)start.x, (int)start.y, (int)goal.m_mapid, (int)goal.x, (int)goal.y, (int)ok, (int)path->m_waypts.size(),
                         (int)path->m_legcount);

    return ok;
}

/* ---- muzzle-flash light maps: count them (each shot adds the weapon's light map for one flash) ---- */
#include "gamez/zNode/node_light.h"

namespace
{
unsigned g_flashes;
unsigned g_slow_until; /* -DSP_SLOWMO=<flash>: frame until which the game runs at 1/50 speed */
}

#ifndef SP_SLOWLEN
#define SP_SLOWLEN 900
#endif

#ifdef SP_SLOWMO
/* -DSP_SLOWMO=<n>: from flash n on, the scheduled tasks (anims, AI, weapons) get 1/50 of the frame
   time for SP_SLOWLEN frames (default 900), so the muzzle flash's light map stays up for a screenshot; the test camera
   looks at the player from the front (-DSP_FLASHCAM_D=<distance>, default 70) */
extern "C" bool __real__ZN14CSched_Manager4TickEf(void *sched, float dT);
extern "C" bool __wrap__ZN14CSched_Manager4TickEf(void *sched, float dT)
{
    if (g_slow_until != 0)
        dT *= 0.02f;

    return __real__ZN14CSched_Manager4TickEf(sched, dT);
}
#endif

extern "C" void __real__ZN3zdb6CWorld11AddLightMapEPNS_9CLightMapE(zdb::CWorld *w, zdb::CLightMap *map);
extern "C" void __wrap__ZN3zdb6CWorld11AddLightMapEPNS_9CLightMapE(zdb::CWorld *w, zdb::CLightMap *map)
{
    __real__ZN3zdb6CWorld11AddLightMapEPNS_9CLightMapE(w, map);

    if (!map->m_isShadow)
    {
        g_flashes++;

        if (g_flashes <= 3 || g_flashes % 10 == 0)
            SOCOM_PORT_TRACE("HOOK SP: flash %u: light map %s (frame %u, %u light maps)", g_flashes, map->m_name ? map->m_name : "?", g_frames,
                             (unsigned)w->m_lightMaps.size());

#ifdef SP_SLOWMO
        if (g_flashes == (unsigned)(SP_SLOWMO))
        {
            g_slow_until = g_frames + SP_SLOWLEN;
            SOCOM_PORT_TRACE("HOOK SP: flash %u: slow motion until frame %u", g_flashes, g_slow_until);
        }
#endif
    }
}

extern "C" void __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat);
extern "C" void __wrap__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat)
{
    __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(body, eye, mat);
    static unsigned int hook_clock1;
    for (unsigned int hook_n = hook_field_step(&hook_clock1); hook_n > 0; hook_n--)
    {
        g_frames++;

        if (g_frames == 1)
            census();

#ifdef SP_GOPT
        /* -DSP_GOPT=<flag>: one of CHUD::StatusLine's debug readouts on from the first frame (gopt's
           doStatusLine, doStatusLineSmall, doAssetReport, doTaskReport, doRenderReport, doFPS);
           -DSP_VISINFO adds ai::visinfo (the small status's AI lines) */
        if (g_frames == 1)
        {
            gopt.SP_GOPT = true;
#ifdef SP_VISINFO
            ai::visinfo = 1;
#endif
            SOCOM_PORT_TRACE("HOOK SP: gopt flag on: status %d small %d asset %d task %d render %d fps %d visinfo %d", (int)gopt.doStatusLine,
                             (int)gopt.doStatusLineSmall, (int)gopt.doAssetReport, (int)gopt.doTaskReport, (int)gopt.doRenderReport,
                             (int)gopt.doFPS, (int)ai::visinfo);
        }
#endif

#ifdef SP_SLOWMO
#ifndef SP_FLASHCAM_D
#define SP_FLASHCAM_D 70.0f
#endif
        if (g_slow_until != 0 && g_frames > g_slow_until)
        {
            g_slow_until = 0;
            SOCOM_PORT_TRACE("HOOK SP: f%u slow motion off", g_frames);
        }

        if (g_flashes >= 1 && body == ftsGetPlayer())
        {
            const CMatrix &m = body->m_node->m_matrix;
            float fx = -m.m_matrix[2][0], fz = -m.m_matrix[2][2];
            float l = sqrtf(fx * fx + fz * fz);
            fx /= l;
            fz /= l;
            freecam_node(body->m_node, fx * SP_FLASHCAM_D + fz * 0.3f * SP_FLASHCAM_D, 0.5f * SP_FLASHCAM_D,
                         fz * SP_FLASHCAM_D - fx * 0.3f * SP_FLASHCAM_D);
        }
#endif

        if (g_frames % 600 == 0)
        {
            struct mallinfo mi = mallinfo();
            SOCOM_PORT_TRACE("HOOK SP: f%u flashes %u, heap in use %d", g_frames, g_flashes, mi.uordblks);
        }

#ifndef SP_NOROUTE
        if (g_frames == SP_ROUTE_AT)
            start_route();

        if (g_route_ai != NULL && g_frames == SP_ROUTE_AT + 15)
            set_route();

        static int s_map = -1;

        if (g_route_ai != NULL && g_frames > SP_ROUTE_AT && (int)g_route_ai->m_mapLocValid.m_mapid != s_map)
        {
            s_map = g_route_ai->m_mapLocValid.m_mapid;
            trace_route("map");
        }

        if (g_route_ai != NULL && g_frames > SP_ROUTE_AT && g_frames <= SP_ROUTE_AT + SP_ROUTE_LEN)
        {
            CSealCtrlAi *ai = ai_of(g_route_ai);

            if (!g_route_done_shown && g_frames > SP_ROUTE_AT + 15 && ai != NULL && ai->m_path.m_state == ::PATH_STATE::COMPLETE)
            {
                g_route_done_shown = 1;
                trace_route("planned");
                dump_path();
            }

            if (g_frames % 60 == 0)
                trace_route("walk");

            if (g_frames == SP_ROUTE_AT + SP_ROUTE_LEN)
                freecam_off();
        }
#endif

        freecam_apply();
    }
}
