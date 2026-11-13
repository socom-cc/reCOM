/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* hook_freecam.h - TEST CAMERA for scratch test hooks (test builds only; never in src/ or a normal build).
 *
 * Puts the game camera at an eye point looking at a target for as long as it is on, without
 * moving the player. Include it in a hook_*.cpp after the game headers (it needs CAppCamera,
 * zdb::CCamera, CNode::SetMatrix), then:
 *
 *   1. link with  -Wl,--wrap=_ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix
 *      and call freecam_apply() at the end of the wrapper (after __real_...). CAppCamera::Tick
 *      (0x1ea480 / camera.cpp) calls CheckDIShoot right after m_camera->SetMatrix, every frame,
 *      non-virtually, so the wrapper is the last word on the camera matrix for the frame (only
 *      the wiggle echo, if running, adds to it). If your hook already wraps CheckDIShoot, just
 *      add the freecam_apply() call there. Define HOOK_FREECAM_WRAP before the include to get a
 *      ready-made wrapper (only when your hook does not wrap CheckDIShoot itself).
 *   2. freecam_look(eye, target) / freecam_look_from(target, dx, dy, dz) to take the camera,
 *      freecam_node(node, dx, dy, dz) to follow a node (eye = node origin + offset, re-read
 *      every frame), freecam_off() to give it back (the follow camera rebuilds its matrix
 *      next frame).
 *
 * The camera's LookAt (CAppCamera::LookAt) builds the matrix; m_wPos becomes the eye while on.
 * The reticle ray of that frame was already cast from the player's view (the wrap runs after
 * the real CheckDIShoot), so aiming and firing are not changed by the test camera.
 * First used by socom-port-fx2 (port/test-hooks/pickups/hook_pickups.cpp, hook_actions.cpp). */
#ifndef HOOK_FREECAM_H
#define HOOK_FREECAM_H

#include "gamez/zCamera/zcam.h"

struct HookFreecam
{
    bool on;
    CPnt3D eye;
    CPnt3D target;
    zdb::CNode *node;  /* non-NULL: target = node origin, eye = target + offset */
    CPnt3D offset;
};

static HookFreecam g_freecam = { false, CPnt3D(0.0f, 0.0f, 0.0f), CPnt3D(0.0f, 0.0f, 0.0f), NULL, CPnt3D(0.0f, 0.0f, 0.0f) };

static inline void freecam_look(const CPnt3D &eye, const CPnt3D &target)
{
    g_freecam.on = true;
    g_freecam.node = NULL;
    g_freecam.eye = eye;
    g_freecam.target = target;
}

static inline void freecam_look_from(const CPnt3D &target, float dx, float dy, float dz)
{
    CPnt3D eye(target.x + dx, target.y + dy, target.z + dz);
    freecam_look(eye, target);
}

static inline void freecam_node(zdb::CNode *node, float dx, float dy, float dz)
{
    g_freecam.on = true;
    g_freecam.node = node;
    g_freecam.offset = CPnt3D(dx, dy, dz);
}

static inline void freecam_off()
{
    g_freecam.on = false;
    g_freecam.node = NULL;
}

static inline void freecam_apply()
{
    if (!g_freecam.on || appCamera == NULL || appCamera->m_camera == NULL)
        return;

    if (g_freecam.node != NULL)
    {
        const float *p = g_freecam.node->m_matrix.m_matrix[3];
        g_freecam.target = CPnt3D(p[0], p[1], p[2]);
        g_freecam.eye = CPnt3D(p[0] + g_freecam.offset.x, p[1] + g_freecam.offset.y, p[2] + g_freecam.offset.z);
    }

    CMatrix m;
    appCamera->LookAt(&g_freecam.eye, &g_freecam.target, m);
    appCamera->m_camera->SetMatrix(&m);
}

#ifdef HOOK_FREECAM_WRAP
extern "C" void __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat);

extern "C" void __wrap__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(CZSealBody *body, CPnt3D *eye, CMatrix *mat)
{
    __real__ZN10CZSealBody12CheckDIShootEP6CPnt3DP7CMatrix(body, eye, mat);
    freecam_apply();
}
#endif

#endif
