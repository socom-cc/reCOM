/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-mod-render, character shadows (render maps) and light maps in
 * m8. Linked with ../state/hook_state.cpp (menus, intro movie, briefing cameras, heap trace). It
 * traces:
 *  - every CWorld::AddShadow (the caster) and CWorld::AddLightMap (name, shadow / reflection bits,
 *    texture) call;
 *  - every 150 frames of the mission (wrap of CZSealBody::CheckDIShoot, once a frame for the
 *    player): the world's render maps and light maps (shadow / plain), CRenderMap::Update and
 *    zVid_FrameRestore calls per frame, the player's render map range, the mean frame time and
 *    the heap in use.
 * Switches: -DRN_NOSHADOW (AddShadow does nothing: the "before" of the character shadows),
 * -DRN_NOLIGHTMAP (AddLightMap skips plain light maps such as the muzzle flash's: their "before"),
 * -DRN_LMDUMP (the fields of the last plain light map added, for three frames),
 * -DRN_CAM=<frame> (test camera on the player from that mission frame: three views of 300 frames
 * each, then given back; -DRN_CAMD=<distance>, default 14; -DRN_CAMLEN=<frames> per view, default 300). */
#include <list>
#include <vector>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zNode/znode.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zNode/node_light.h"
#include "gamez/zNode/node_shadow.h"
#include "gamez/zVideo/zvid.h"
#include "gamez/zVisual/zvis.h"
#include "gamez/zTexture/ztex.h"
#include "gamez/zCamera/zcam.h"
#include <stdio.h>
#include <string.h>
#include <malloc.h>

#include "hook_freecam.h"

#ifndef RN_CAMD
#define RN_CAMD 14.0f
#endif
#ifndef RN_CAMLEN
#define RN_CAMLEN 300
#endif

namespace
{
unsigned g_frames;
zdb::CLightMap *g_watch; /* -DRN_LMDUMP: the last plain light map added, dumped for 3 frames */
int g_watch_frames;
unsigned g_updates, g_restores;
float g_time;
}

extern "C" void __real__ZN3zdb6CWorld9AddShadowEPNS_5CNodeE(zdb::CWorld *w, zdb::CNode *node);
extern "C" void __wrap__ZN3zdb6CWorld9AddShadowEPNS_5CNodeE(zdb::CWorld *w, zdb::CNode *node)
{
    SOCOM_PORT_TRACE("HOOK RN: AddShadow %s (maps %d)%s", node && node->m_name ? node->m_name : "?", (int)w->m_shadows.size(),
#ifdef RN_NOSHADOW
                     " - skipped (RN_NOSHADOW)");
    return;
#else
                     "");
    __real__ZN3zdb6CWorld9AddShadowEPNS_5CNodeE(w, node);
#endif
}

extern "C" void __real__ZN3zdb6CWorld11AddLightMapEPNS_9CLightMapE(zdb::CWorld *w, zdb::CLightMap *map);
extern "C" void __wrap__ZN3zdb6CWorld11AddLightMapEPNS_9CLightMapE(zdb::CWorld *w, zdb::CLightMap *map)
{
#ifdef RN_NOLIGHTMAP
    if (!map->m_isShadow)
    {
        SOCOM_PORT_TRACE("HOOK RN: AddLightMap %s skipped (RN_NOLIGHTMAP)", map->m_name ? map->m_name : "?");
        return;
    }
#endif
    __real__ZN3zdb6CWorld11AddLightMapEPNS_9CLightMapE(w, map);
#ifdef RN_LMDUMP
    if (!map->m_isShadow)
    {
        g_watch = map;
        g_watch_frames = 3;
    }
#endif
    SOCOM_PORT_TRACE("HOOK RN: AddLightMap %s shadow %d reflection %d tex %s range %.1f (maps %d)", map->m_name ? map->m_name : "?",
                     (int)map->m_isShadow, (int)map->m_isReflection, map->m_pTex && map->m_pTex->m_name ? map->m_pTex->m_name : "-",
                     map->m_maxRange, (int)w->m_lightMaps.size());
}

extern "C" void __real__ZN3zdb10CRenderMap6UpdateEv(zdb::CRenderMap *map);
extern "C" void __wrap__ZN3zdb10CRenderMap6UpdateEv(zdb::CRenderMap *map)
{
    __real__ZN3zdb10CRenderMap6UpdateEv(map);
    g_updates++;
}

extern "C" void __real__Z17zVid_FrameRestorev();
extern "C" void __wrap__Z17zVid_FrameRestorev()
{
    __real__Z17zVid_FrameRestorev();
    g_restores++;
}

extern "C" void __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat);
extern "C" void __wrap__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat)
{
    __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(body, eye, mat);
    g_frames++;
    g_time += zVid.frameTime;

#ifdef RN_CAM
    if (g_frames >= (unsigned)(RN_CAM) && g_frames < (unsigned)(RN_CAM) + 3 * (RN_CAMLEN))
    {
        static const float view[3][3] = { { -1.0f, 1.0f, -0.2f }, { 0.3f, 1.0f, -1.0f }, { -0.7f, 0.5f, 0.7f } };
        int s = (g_frames - (RN_CAM)) / (RN_CAMLEN);
        freecam_node(body->m_node, view[s][0] * RN_CAMD, view[s][1] * RN_CAMD, view[s][2] * RN_CAMD);

        if ((g_frames - (RN_CAM)) % (RN_CAMLEN) == 0)
        {
            const float *p = body->m_node->m_matrix.m_matrix[3];
            SOCOM_PORT_TRACE("HOOK RN: cam view %d on the player at %.1f %.1f %.1f (frame %u)", s, p[0], p[1], p[2], g_frames);
        }
    }
    else if (g_freecam.on)
    {
        freecam_off();
    }
#endif

    freecam_apply();

#ifdef RN_LMDUMP
    if (g_watch != NULL && g_watch_frames > 0)
    {
        zdb::CLightMap *m = g_watch;
        g_watch_frames--;
        SOCOM_PORT_TRACE("HOOK RN: lm %s range %g..%g inv %g invd %g diff %g %g %g op %g pos %g %g %g tex %p %ux%u qwc %u blend %08x%08x active %d",
                         m->m_name ? m->m_name : "?", m->m_minRange, m->m_maxRange, m->m_invMaxRange, m->m_invDeltaRange,
                         m->m_diffuse.x, m->m_diffuse.y, m->m_diffuse.z, m->m_opacity, m->m_matrix.m_matrix[3][0],
                         m->m_matrix.m_matrix[3][1], m->m_matrix.m_matrix[3][2], m->m_pTex,
                         m->m_pTex ? m->m_pTex->m_width : 0, m->m_pTex ? m->m_pTex->m_height : 0,
                         m->m_pTex ? (unsigned)m->m_pTex->m_dmaRef.u16[0] : 0,
                         (unsigned)(m->m_blendmode.m_alphaWORD >> 32), (unsigned)m->m_blendmode.m_alphaWORD, (int)m->m_active);
    }
#endif

    if (g_frames % 150 == 0)
    {
        zdb::CWorld *w = zdb::CWorld::m_world;
        int shadow = 0, plain = 0;

        for (zdb::CLightMapVector::iterator it = w->m_lightMaps.begin(); it != w->m_lightMaps.end(); ++it)
        {
            if ((*it)->m_isShadow)
                shadow++;
            else
                plain++;
        }

        float range = -1.0f;

        for (zdb::CRenderMapVector::iterator it = w->m_shadows.begin(); it != w->m_shadows.end(); ++it)
        {
            if ((*it)->m_node == body->m_node)
                range = (*it)->m_maxRange;
        }

        struct mallinfo mi = mallinfo();
        SOCOM_PORT_TRACE("HOOK RN: f %u render maps %d light maps %d shadow + %d plain, updates %.2f restores %.2f per frame, player map range %.1f, frame %.4f s, in use %d",
                         g_frames, (int)w->m_shadows.size(), shadow, plain, g_updates / 150.0f, g_restores / 150.0f, range,
                         g_time / 150.0f, mi.uordblks);
        g_updates = g_restores = 0;
        g_time = 0.0f;
    }
}
