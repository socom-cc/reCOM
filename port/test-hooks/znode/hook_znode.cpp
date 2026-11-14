/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-mod-znode, the zNode scene-graph pieces in m8. Linked with
 * ../state/hook_state.cpp (menus, intro movie, briefing cameras, heap trace). It traces:
 *  - after LoadWorld (wrap of CWorld::GenerateLightList, its last world call): the level-of-detail,
 *    material and scrolling-texture bands read by CSaveLoad::Load, the running texture effects,
 *    landmarks, nodes the far plane must not clip, lights and the cells that list them;
 *  - every 150 frames of the mission (wrap of CZSealBody::CheckDIShoot, which runs once a frame
 *    for the player): the wind vector, the scrolling effects' first UV, the DrawLOD calls of the
 *    window (and how many said "not drawn"), the mean frame time.
 * Switches: -DZN_NOLOD (DrawLOD always draws: the "before" of the level-of-detail bands),
 * -DZN_CAM=<frame> (test camera on the scrolling computer screen from that mission frame for
 * 1800 frames, four sides 450 frames each, then given back; -DZN_CAMD=<distance>, default 6). */
#include <list>
#include <vector>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zNode/znode.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zNode/node_model.h"
#include "gamez/zNode/node_light.h"
#include "gamez/zGrid/zgrid.h"
#include "gamez/zVideo/zvid.h"
#include "gamez/zVisual/zvis.h"
#include "gamez/zTexture/ztex.h"
#include "gamez/zCamera/zcam.h"
#include <stdio.h>
#include <string.h>

#include "hook_freecam.h"

#ifndef ZN_CAMD
#define ZN_CAMD 6.0f
#endif

zdb::CNode *find_node(zdb::CNode *, const char *);

namespace
{
unsigned g_frames;
unsigned g_lod_calls, g_lod_hidden;
float g_time;
zdb::CNode *g_screen;

void census(zdb::CWorld *w)
{
    zdb::CLOD_Object &lod = w->m_LOD_Object;
    SOCOM_PORT_TRACE("HOOK ZN: bands LOD %d material %d scroll %d; texfx running %d free %d",
           (int)lod.size(), (int)w->m_Material_Object.size(), (int)w->m_ScrollingTexture_Object.size(),
           (int)zdb::CTextureFX::m_texfxpool.size(),
           zdb::CTextureFX::m_texfxfreepool != NULL ? (int)zdb::CTextureFX::m_texfxfreepool->size() : -1);

    for (unsigned i = 0; i < lod.size() && i < 32; i++)
    {
        zdb::CLOD_band &b = lod[i];
        SOCOM_PORT_TRACE("HOOK ZN: LOD %u min %.0f..%.0f max %.0f..%.0f fade %d%d", i + 1, b.m_minRangeNearSq,
               b.m_minRangeFarSq, b.m_maxRangeNearSq, b.m_maxRangeFarSq, b.m_minFade, b.m_maxFade);
    }

    for (unsigned i = 0; i < w->m_ScrollingTexture_Object.size(); i++)
    {
        zdb::CScrollingTexture_band &s = w->m_ScrollingTexture_Object[i];
        zdb::CModel *model = zdb::CWorld::GetModel(s.m_modelname);
        zdb::CNode *node = find_node(model, s.m_nodename);
        SOCOM_PORT_TRACE("HOOK ZN: scroll %s/%s du %.2f dv %.2f model %p (%d instances) node %p (%d visuals, vtype %d)",
               s.m_modelname, s.m_nodename, s.m_du, s.m_dv, model, model ? (int)model->m_list.size() : -1, node,
               node ? (int)node->m_visual.size() : -1,
               node && node->m_visual.size() ? (int)node->m_visual[0]->m_vtype : -9);

        if (node != NULL)
            g_screen = node;
    }

    for (std::list<zdb::CTextureFX *>::iterator it = zdb::CTextureFX::m_texfxpool.begin(); it != zdb::CTextureFX::m_texfxpool.end(); ++it)
        SOCOM_PORT_TRACE("HOOK ZN: texfx %p visual %p vid %u type %u du %.2f dv %.2f", *it, (*it)->m_visual, (*it)->m_vid,
               (*it)->m_type, (*it)->m_du, (*it)->m_dv);

    int cells = 0, listed = 0;

    for (zdb::CNodeVector::iterator it = w->m_child.begin(); it != w->m_child.end(); ++it)
    {
        zdb::CCell *cell = dynamic_cast<zdb::CCell *>(*it);

        if (cell != NULL && cell->m_lightList.size() != 0)
        {
            cells++;
            listed += cell->m_lightList.size();
        }
    }

    SOCOM_PORT_TRACE("HOOK ZN: landmarks %d, no-far-clip nodes %u, lights %d (in %d cells, %d entries), world children %d",
           (int)w->m_landmarks.size(), w->m_numNoFarClipNodes, (int)w->m_lights.size(), cells, listed, (int)w->m_child.size());

    for (unsigned i = 0; i < w->m_landmarks.size() && i < 12; i++)
    {
        zdb::CNode *n = w->m_landmarks[i];
        SOCOM_PORT_TRACE("HOOK ZN: landmark %s at %.1f %.1f %.1f r %.1f", n->m_name ? n->m_name : "?", n->m_matrix.m_matrix[3][0],
               n->m_matrix.m_matrix[3][1], n->m_matrix.m_matrix[3][2], n->GetRadius());
    }

    for (zdb::CLightList::iterator it = w->m_lights.begin(); it != w->m_lights.end(); ++it)
    {
        zdb::CLight *l = *it;
        SOCOM_PORT_TRACE("HOOK ZN: light %s at %.1f %.1f %.1f range %.1f..%.1f diffuse %.0f %.0f %.0f", l->m_name ? l->m_name : "?",
               l->m_WorldPosition.x, l->m_WorldPosition.y, l->m_WorldPosition.z, l->m_minRange, l->m_maxRange,
               l->m_diffuse.x, l->m_diffuse.y, l->m_diffuse.z);
    }

    zdb::CCamera *cam = w->m_camera;
    SOCOM_PORT_TRACE("HOOK ZN: camera mid %.0f far %.0f", cam->m_mid_plane, cam->m_far_plane);
}
}

extern "C" zdb::CLightList *__real__ZN3zdb6CWorld17GenerateLightListEv(zdb::CWorld *w);
extern "C" zdb::CLightList *__wrap__ZN3zdb6CWorld17GenerateLightListEv(zdb::CWorld *w)
{
    zdb::CLightList *r = __real__ZN3zdb6CWorld17GenerateLightListEv(w);
    census(w);
    g_frames = 0;
    return r;
}

extern "C" bool __real__ZN3zdb7CVisual7DrawLODEPNS_9CLOD_bandEfPf(zdb::CVisual *v, zdb::CLOD_band *b, float range, float *op);
extern "C" bool __wrap__ZN3zdb7CVisual7DrawLODEPNS_9CLOD_bandEfPf(zdb::CVisual *v, zdb::CLOD_band *b, float range, float *op)
{
    bool r = __real__ZN3zdb7CVisual7DrawLODEPNS_9CLOD_bandEfPf(v, b, range, op);
    g_lod_calls++;

    if (!r)
        g_lod_hidden++;
#ifdef ZN_NOLOD
    return true;
#else
    return r;
#endif
}

extern "C" void __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat);
extern "C" void __wrap__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat)
{
    __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(body, eye, mat);
    g_frames++;
    g_time += zVid.frameTime;

#ifdef ZN_CAM
    if (g_screen != NULL && g_frames >= (unsigned)(ZN_CAM) && g_frames < (unsigned)(ZN_CAM) + 1800)
    {
        static const float side[4][2] = { { 1.0f, 0.0f }, { 0.0f, 1.0f }, { -1.0f, 0.0f }, { 0.0f, -1.0f } };
        int s = (g_frames - (ZN_CAM)) / 450;
        CMatrix mtw;
        sceVu0UnitMatrix(mtw.m_matrix);

        if (g_screen->BuildMTW(mtw) == NULL)
            sceVu0CopyMatrix(mtw.m_matrix, g_screen->m_matrix.m_matrix);

        const float *p = mtw.m_matrix[3];
        CPnt3D target(p[0], p[1], p[2]);
        freecam_look_from(target, side[s][0] * ZN_CAMD, 1.0f, side[s][1] * ZN_CAMD);

        if ((g_frames - (ZN_CAM)) % 450 == 0)
            SOCOM_PORT_TRACE("HOOK ZN: cam side %d on %s at %.1f %.1f %.1f (frame %u)", s, g_screen->m_name ? g_screen->m_name : "?", p[0], p[1], p[2], g_frames);
    }
    else if (g_freecam.on)
    {
        freecam_off();
    }
#endif

    freecam_apply();

    if (g_frames % 150 == 0)
    {
        zdb::CWorld *w = zdb::CWorld::m_world;
        const CPnt4D &wind = w->m_Wind.m_Wind;
        int u = 0, v = 0;

        if (!zdb::CTextureFX::m_texfxpool.empty())
        {
            static zdb::CVisData data;
            zdb::CTextureFX *fx = zdb::CTextureFX::m_texfxpool.front();
            zdb::CVisData *d = data.SelectVertex(fx->m_visual, fx->m_vid, 0);

            if (d != NULL)
            {
                u = d->m_vertex[4];
                v = d->m_vertex[5];
            }
        }

        SOCOM_PORT_TRACE("HOOK ZN: f %u wind %.2f %.2f %.2f (az %.2f+%.2f speed %.2f+%.2f) uv0 %d %d lod %u hidden %u frame %.4f s",
               g_frames, wind.x, wind.y, wind.z, w->m_Wind.m_Azimuth, w->m_Wind.m_AzimuthOffset, w->m_Wind.m_Speed,
               w->m_Wind.m_SpeedOffset, u, v, g_lod_calls / 150, g_lod_hidden / 150, g_time / 150.0f);
        g_lod_calls = g_lod_hidden = 0;
        g_time = 0.0f;
    }
}
