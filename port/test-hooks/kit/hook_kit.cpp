/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-kit.
 * Wraps scePadRead: the hook presses buttons itself (g_press, with full analog pressure) and CROSS
 *  while a cinematic plays (CCinematicState::Tick wrap) or a mission camera plays (skip).
 * Wraps CameraZoom::AttachSeal: seal census, player invincible.
 * Wraps CZSealBody::GetTerrainMotionFactor (per seal frame): the kit script (steps[] below): zoom
 *  steps per weapon, items put into kit slots (CZKit::SetItem/SetItemAmmo) and selected
 *  (SetCurItemByIndex, what the R2 menu calls), fired / thrown with R1; traces kit, zoom and HUD.
 * Test camera (hook_freecam.h) on placed / thrown explosives (step CAMX). */
#include <map>
#include <string>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zWeapon/zweapon.h"
#include "Apps/FTS/hud/hud.h"
#include "gamez/zWeapon/zwep_projectilelist.h"
#include "gamez/zIntersect/zintersect.h"
#include <string.h>
#include <math.h>
#include <libvu0.h>
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);
extern "C" bool __real__ZN15CCinematicState4TickEf(void *state, float dT);

namespace
{
CZSealBody *g_seals[64];
int g_nseals;
unsigned short g_press;   /* buttons (rdata[2] << 8 | rdata[3] bits) held for g_press_left reads */
int g_press_left;
unsigned int g_reads;
bool g_movie;
unsigned int g_movie_last;
unsigned int g_cam_last;
unsigned int g_cam_seen;

const unsigned short B_R1 = 0x0008;
const unsigned short B_CROSS = 0x0040;
const unsigned short B_UP = 0x1000;
const unsigned short B_DOWN = 0x4000;

enum Op { K_END, K_TRACE, K_UP, K_DOWN, K_R1, K_R1HOLD, K_SEL, K_SETITEM, K_NIGHT, K_FINDSEL, K_CAMX, K_CAMOFF, K_ZOOMOUT, K_KITLIST, K_WALL, K_ENEMY, K_CAMEXPL, K_ENEMYTRACE };
struct Step { int wait; Op op; int a; int b; const char *why; };

/* frame waits are player frames (~60/s) after the previous step */
#define KIT_STEPS_SURVEY \
    { 60, K_KITLIST, 0, 0, "kit at start" }, \
    { 1, K_FINDSEL, 102, 0, "M40A1 (armory) selected" }, \
    { 1, K_SETITEM, 102, 0, "M40A1 into slot 0 if the armory did not" }, \
    { 60, K_TRACE, 0, 0, "M40A1 in hand" }, \
    { 1, K_UP, 0, 0, "M40A1 zoom 1 (first person)" }, \
    { 90, K_TRACE, 0, 0, "first person" }, \
    { 1, K_UP, 0, 0, "M40A1 zoom 2 (6x)" }, \
    { 150, K_TRACE, 0, 0, "M40A1 6x" }, \
    { 1, K_UP, 0, 0, "M40A1 zoom 3 (16x)" }, \
    { 150, K_TRACE, 0, 0, "M40A1 16x" }, \
    { 1, K_R1, 0, 0, "M40A1 shot scoped" }, \
    { 90, K_TRACE, 0, 0, "after the scoped shot" }, \
    { 1, K_ZOOMOUT, 0, 0, "back to third person" }, \
    { 120, K_SETITEM, 62, 0, "M4A1 SD into slot 0" }, \
    { 1, K_SEL, 0, 0, "M4A1 SD" }, \
    { 60, K_UP, 0, 0, "M4A1 SD zoom 1" }, \
    { 60, K_UP, 0, 0, "M4A1 SD zoom 2 (2.5x)" }, \
    { 150, K_TRACE, 0, 0, "M4A1 SD 2.5x" }, \
    { 1, K_ZOOMOUT, 0, 0, "back" }, \
    { 120, K_SETITEM, 105, 5, "SR-25 SD into slot 5" }, \
    { 1, K_SEL, 5, 0, "SR-25 SD" }, \
    { 60, K_UP, 0, 0, "SR-25 SD zoom 1" }, \
    { 60, K_UP, 0, 0, "SR-25 SD zoom 2 (8x)" }, \
    { 150, K_TRACE, 0, 0, "SR-25 SD 8x" }, \
    { 1, K_R1, 0, 0, "SR-25 SD shot" }, \
    { 60, K_ZOOMOUT, 0, 0, "back" }, \
    { 120, K_SEL, 1, 0, "pistol (slot 1)" }, \
    { 60, K_UP, 0, 0, "pistol zoom 1" }, \
    { 60, K_UP, 0, 0, "pistol zoom 2 (binoculars)" }, \
    { 150, K_TRACE, 0, 0, "binoculars" }, \
    { 1, K_ZOOMOUT, 0, 0, "back" }, \
    { 90, K_NIGHT, 1, 0, "TEST: night mission flag on (m8 is a day mission)" }, \
    { 1, K_SEL, 0, 0, "M4A1 SD" }, \
    { 60, K_UP, 0, 0, "night zoom 1" }, \
    { 60, K_UP, 0, 0, "night zoom 2 (NVG)" }, \
    { 150, K_TRACE, 0, 0, "NVG" }, \
    { 1, K_UP, 0, 0, "night zoom 3 (2.5x starlight)" }, \
    { 150, K_TRACE, 0, 0, "starlight scope" }, \
    { 1, K_ZOOMOUT, 0, 0, "back" }, \
    { 60, K_NIGHT, 0, 0, "night flag off" }, \
    { 60, K_SETITEM, 122, 6, "AN-M8 smoke into slot 6" }, \
    { 1, K_SEL, 6, 0, "smoke" }, \
    { 60, K_R1HOLD, 30, 0, "throw smoke" }, \
    { 1, K_CAMX, 0, 0, "camera on the projectile" }, \
    { 420, K_TRACE, 0, 0, "smoke out" }, \
    { 1, K_CAMOFF, 0, 0, "camera back" }, \
    { 60, K_SETITEM, 126, 7, "HE into slot 7" }, \
    { 1, K_SEL, 7, 0, "HE" }, \
    { 60, K_R1HOLD, 30, 0, "throw HE" }, \
    { 1, K_CAMX, 0, 0, "camera on the projectile" }, \
    { 420, K_TRACE, 0, 0, "HE out" }, \
    { 1, K_CAMOFF, 0, 0, "camera back" }, \
    { 60, K_FINDSEL, 151, 0, "C4" }, \
    { 60, K_R1, 0, 0, "use C4" }, \
    { 180, K_TRACE, 0, 0, "after C4" }, \
    { 1, K_SETITEM, 187, 8, "detonator into slot 8" }, \
    { 1, K_SEL, 8, 0, "detonator" }, \
    { 60, K_R1, 0, 0, "detonate" }, \
    { 180, K_TRACE, 0, 0, "after detonator" }, \
    { 1, K_SETITEM, 152, 9, "satchel into slot 9" }, \
    { 1, K_SEL, 9, 0, "satchel" }, \
    { 60, K_R1, 0, 0, "use satchel" }, \
    { 180, K_TRACE, 0, 0, "after satchel" }, \
    { 1, K_SEL, 0, 0, "rifle again" }, \
    { 60, K_KITLIST, 0, 0, "kit at the end" }, \
    { 0, K_END, 0, 0, "" }
/* run 2 (-DKIT_RUN2): scopes for the record, binoculars, C4 on a wall next to an enemy, then a
 * claymore (TEST: m8 does not enable it) set off with the detonator next to another enemy */
#define KIT_STEPS_RUN2 \
    { 60, K_KITLIST, 0, 0, "kit at start" }, \
    { 1, K_FINDSEL, 102, 0, "M40A1 (armory)" }, \
    { 60, K_UP, 0, 0, "M40A1 zoom 1" }, \
    { 60, K_UP, 0, 0, "M40A1 zoom 2 (6x)" }, \
    { 200, K_TRACE, 0, 0, "M40A1 6x" }, \
    { 1, K_UP, 0, 0, "M40A1 zoom 3 (16x)" }, \
    { 200, K_TRACE, 0, 0, "M40A1 16x" }, \
    { 1, K_ZOOMOUT, 0, 0, "back" }, \
    { 120, K_SEL, 1, 0, "pistol" }, \
    { 120, K_UP, 0, 0, "pistol zoom 1" }, \
    { 60, K_UP, 0, 0, "pistol zoom 2 (binoculars)" }, \
    { 200, K_TRACE, 0, 0, "binoculars" }, \
    { 1, K_ZOOMOUT, 0, 0, "back" }, \
    { 120, K_WALL, 10, 0, "player 10 from the nearest wall, facing it" }, \
    { 30, K_ENEMY, 0, 0, "an enemy beside the wall spot" }, \
    { 30, K_FINDSEL, 151, 0, "C4" }, \
    { 120, K_R1, 0, 0, "use C4" }, \
    { 90, K_TRACE, 0, 0, "after C4 use" }, \
    { 1, K_CAMEXPL, 0, 0, "camera on the C4" }, \
    { 1, K_ENEMYTRACE, 0, 0, "enemy before" }, \
    { 200, K_ENEMY, 0, 1, "the enemy back beside the C4" }, \
    { 1, K_ENEMYTRACE, 0, 0, "enemy at the C4" }, \
    { 150, K_ENEMYTRACE, 0, 0, "enemy after the C4" }, \
    { 150, K_ENEMYTRACE, 0, 0, "enemy later" }, \
    { 60, K_CAMOFF, 0, 0, "camera back" }, \
    { 1, K_SETITEM, 153, 5, "TEST: claymore into slot 5" }, \
    { 1, K_SETITEM, 187, 6, "TEST: detonator into slot 6" }, \
    { 1, K_SEL, 5, 0, "claymore" }, \
    { 120, K_R1, 0, 0, "place claymore" }, \
    { 150, K_KITLIST, 0, 0, "after the claymore (detonator selected?)" }, \
    { 1, K_CAMEXPL, 0, 0, "camera on the claymore" }, \
    { 1, K_ENEMY, 1, 0, "another enemy at the claymore" }, \
    { 30, K_ENEMYTRACE, 0, 0, "enemy before" }, \
    { 1, K_R1, 0, 0, "detonator" }, \
    { 90, K_ENEMYTRACE, 0, 0, "enemy after the claymore" }, \
    { 150, K_ENEMYTRACE, 0, 0, "enemy later" }, \
    { 60, K_CAMOFF, 0, 0, "camera back" }, \
    { 1, K_SEL, 4, 0, "M67" }, \
    { 150, K_R1HOLD, 150, 0, "hold R1 5 s: the throw-power bar" }, \
    { 120, K_TRACE, 0, 0, "bar full" }, \
    { 240, K_KITLIST, 0, 0, "kit at the end" }, \
    { 0, K_END, 0, 0, "" }
#ifdef KIT_RUN2
#define KIT_STEPS KIT_STEPS_RUN2
#else
#define KIT_STEPS KIT_STEPS_SURVEY
#endif
const Step steps[] = { KIT_STEPS };

/* nearest wall-like hit (|n.y| < 0.3) of 72 level rays from the player's chest, within 600 */
bool find_wall(CZSealBody *body, CPnt3D &hitpos, CPnt3D &hitnorm, const char **mname)
{
    zdb::CNode *node = body->m_node;
    bool was = node->SetActive(false);
    CPnt3D p = *body->GetPosW();
    CPnt3D from(p.x, p.y + 15.0f, p.z);
    float best = 1e30f;
    zdb::DiIntersect *wdi = zdb::CWorld::m_world->m_diInt;
    u32 chars = wdi->m_IntersectCharacters;
    wdi->m_IntersectCharacters = 0;

    for (int i = 0; i < 72; i++)
    {
        float a = (float)i * 6.2831853f / 72.0f;
        CPnt3D to(from.x + sinf(a) * 600.0f, from.y, from.z + cosf(a) * 600.0f);
        zdb::IntersectStruct *hit = zdb::CWorld::m_world->GetIntersect(&from, &to);

        if (hit == NULL || fabsf(hit->m_norm.y) > 0.3f)
            continue;

        u32 index = hit->GetMaterial();
        CMaterialEx *m = CMaterialExArray::m_materialex_list[index < CMaterialExArray::m_materialex_list.size() ? index : 0];

        if (index == 1 || m->m_volumetric || m->m_liquid || strcmp(m->m_name, "INVISIBLE_DI") == 0 || strcmp(m->m_name, "PERSON") == 0)
            continue;

        float dx = hit->m_pos.x - from.x, dz = hit->m_pos.z - from.z;
        float d = dx * dx + dz * dz;

        if (d < best)
        {
            best = d;
            hitpos = hit->m_pos;
            hitnorm = hit->m_norm;
            *mname = m->m_name;
        }
    }

    wdi->m_IntersectCharacters = chars;
    node->SetActive(was);
    return best < 1e29f;
}

/* put a seal at target (on the ground there) facing along dir */
void put_seal(CZSealBody *seal, CPnt3D target, CPnt3D dir)
{
    zdb::CNode *node = seal->m_node;
    bool was = node->SetActive(false);
    CPnt3D probe(target.x, target.y + 30.0f, target.z);
    float keep_alt = seal->m_alt;
    seal->m_alt = probe.y;
    zdb::IntersectStruct *ground = seal->SealGetAltitude(&probe, 1.0f);
    seal->m_alt = keep_alt;
    node->SetActive(was);

    if (ground != NULL)
        target.y = ground->m_pos.y;

    CQuat turn;
    float score = -2.0f;

    for (int k = 0; k < 72; k++)
    {
        CQuat q;
        q.MakeYRot((float)k * 6.2831853f / 72.0f);
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
    CPnt3D at = target;
    at.y += 11.0f;
    seal->m_alt = at.y;
    zdb::IntersectStruct *g = seal->SealGetAltitude(&at, 1.0f);

    if (g != NULL)
    {
        seal->m_last_altitude.m_pos = g->m_pos;
        seal->m_last_altitude.m_norm = g->m_norm;
        seal->m_last_altitude.m_poly = g->m_poly;
        seal->m_last_altitude.m_node = g->m_node;
        seal->m_alt = g->m_pos.y;
    }
}

CPnt3D g_wallpos, g_wallnorm;
CZSealBody *g_enemy;
int g_used_enemy[4];
int g_nused;

const char *nm(CZSealBody *s)
{
    return s != NULL && s->m_node != NULL && s->m_node->m_name != NULL ? s->m_node->m_name : "-";
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

void press(unsigned short bits, int reads, const char *why, int frame)
{
    g_press = bits;
    g_press_left = reads;
    SOCOM_PORT_TRACE("HOOK: f%d press %04x x%d (%s) at read %u", frame, bits, reads, why, g_reads);
}

const char *itemname(CZFTSWeapon *w)
{
    return w != NULL && w->GetName() != NULL ? w->GetName() : "-";
}

void kitlist(CZSealBody *body, int frame, const char *why)
{
    CZKit &k = body->m_kit;
    SOCOM_PORT_TRACE("HOOK: f%d KIT (%s): %d items, selected %d", frame, why, k.m_num_items, k.m_selected_item);

    for (int i = 0; i < k.m_num_items && i < 30; i++)
    {
        CZFTSWeapon *w = k.m_item[i];

        if (w == NULL)
            continue;

        SOCOM_PORT_TRACE("HOOK:   slot %d %s id %d type %d zooms %d mag %d mags %d/%d/%d selectable %d",
            i, itemname(w), (int)(u8)w->m_ID, (int)w->m_type, (int)w->m_zoommode.size(),
            k.m_reloads[i][k.m_currentmag[i]], k.m_reloads[i][0], k.m_reloads[i][1], k.m_reloads[i][2],
            (int)k.isSelectableItem(i));
    }
}

void trace(CZSealBody *body, int frame, const char *why)
{
    CZKit &k = body->m_kit;
    CZFTSWeapon *w = k.m_item[k.m_selected_item];
    CHUD *hud = theHUD;
    SOCOM_PORT_TRACE("HOOK: f%d %s: item %d %s mag %d, zoom state %d range %.1f cam %.2f->%.2f view %d, ret type %d (kit %d), hud mode %d, nvg %d binocs %d lensfx %d scaled %d (%.2f %.2f %.2f), scope poly %d, zoom text %d '%s', range text %d, wait fire %d t %.2f",
        frame, why, k.m_selected_item, itemname(w), k.m_reloads[k.m_selected_item][k.m_currentmag[k.m_selected_item]],
        (int)body->m_zoomstate, body->m_zoom_range, CameraZoom::m_current, CameraZoom::m_goal, (int)appCamera->m_ctrl_view,
        hud != NULL ? hud->m_bitmapReticule.m_rettype : -9, k.m_curitemreticule, hud != NULL ? (int)hud->m_hudmode : -9,
        (int)k.NVG_Enabled(), (int)k.IsUsingBinocs(), (int)k.m_lensfx_enable, (int)zdb::CVisual::m_applyScaleColor,
        zdb::CVisual::m_scaleColor[0], zdb::CVisual::m_scaleColor[1], zdb::CVisual::m_scaleColor[2],
        hud != NULL ? (int)hud->m_bitmapReticule.m_scopepoly[0].IsOn() : -9,
        hud != NULL ? (int)hud->m_zoomleveltext.IsOn() : -9, "",
        hud != NULL ? (int)hud->m_rangetext.IsOn() : -9, (int)k.m_waiting_to_fire, k.m_firetime);
}

/* the newest projectile in flight (for the test camera) */
zdb::CNode *g_camnode;
}

extern "C" bool __wrap__ZN15CCinematicState4TickEf(void *state, float dT)
{
    g_movie = true;
    bool r = __real__ZN15CCinematicState4TickEf(state, dT);

    if (!r)
        g_movie = false;

    return r;
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port == 0)
    {
        g_reads++;

        /* CROSS skips a cinematic and the mission cameras (their on-screen X) */
        bool cams = theHUD != NULL && theHUD->m_missioncams.IsPlaying() != 0;

        if (cams)
            g_cam_seen = g_reads;

        bool movie = g_movie || (g_nseals > 0 && g_cam_seen == 0 && !cams); /* the mission-start movie plays between the census and the cameras */

        if ((movie && g_reads >= g_movie_last + 40) || (cams && g_reads >= g_cam_last + 60))
        {
            if (movie)
                g_movie_last = g_reads;
            else
                g_cam_last = g_reads;

            SOCOM_PORT_TRACE("HOOK: CROSS skips the %s at read %u", movie ? "cinematic" : "mission camera", g_reads);
            g_press = B_CROSS;
            g_press_left = 3;
        }

        if (g_press_left > 0)
        {
            unsigned short held = (unsigned short)(~((rdata[2] << 8) | rdata[3]));
            held |= g_press;
            rdata[2] = (unsigned char)~(held >> 8);
            rdata[3] = (unsigned char)~held;

            if (g_press & B_R1)
                rdata[17] = 0xff; /* K_R1 pressure */

            g_press_left--;
        }
    }

    return r;
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
    SOCOM_PORT_TRACE("HOOK: census %d seals, player %s team 0x%x (invincible), night %d", g_nseals, nm(player), player->m_team,
        (int)world->m_night_mission);
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    bool busy = theHUD == NULL || theHUD->m_missioncams.IsPlaying() != 0 || (g_cam_seen != 0 && g_reads < g_cam_seen + 90)
        || (g_cam_seen == 0 && g_reads < 1200);

    if (body == ftsGetPlayer() && !busy)
    {
        static int frame = 0;
        static int step = 0;
        static int at = 0;
        static int zoomouts = 0;
        frame++;
        body->m_invincible = 1;

        if (zoomouts > 0 && frame % 20 == 0)
        {
            if ((s8)body->m_zoomstate > 0)
            {
                press(B_DOWN, 3, "zoom out", frame);
                zoomouts--;
            }
            else
            {
                zoomouts = 0;
                trace(body, frame, "third person again");
            }
        }

        if (steps[step].op != K_END && frame >= at + steps[step].wait)
        {
            const Step &s = steps[step];
            CZKit &k = body->m_kit;
            at = frame;
            step++;

            switch (s.op)
            {
            case K_TRACE:
                trace(body, frame, s.why);
                break;
            case K_KITLIST:
                kitlist(body, frame, s.why);
                break;
            case K_UP:
                press(B_UP, 3, s.why, frame);
                break;
            case K_DOWN:
                press(B_DOWN, 3, s.why, frame);
                break;
            case K_R1:
                press(B_R1, 3, s.why, frame);
                break;
            case K_R1HOLD:
                press(B_R1, s.a, s.why, frame);
                break;
            case K_ZOOMOUT:
                zoomouts = 6;
                SOCOM_PORT_TRACE("HOOK: f%d %s", frame, s.why);
                break;
            case K_SEL:
                k.SetCurItemByIndex(s.a);
                SOCOM_PORT_TRACE("HOOK: f%d select slot %d (%s): %s", frame, s.a, s.why, itemname(k.m_item[k.m_selected_item]));
                break;
            case K_FINDSEL:
            {
                int found = -1;

                for (int i = 0; i < k.m_num_items; i++)
                    if (k.m_item[i] != NULL && (int)(u8)k.m_item[i]->m_ID == s.a)
                        found = i;

                if (found >= 0)
                    k.SetCurItemByIndex(found);

                SOCOM_PORT_TRACE("HOOK: f%d find id %d (%s): slot %d", frame, s.a, s.why, found);
                break;
            }
            case K_SETITEM:
            {
                bool have = false;

                for (int i = 0; i < k.m_num_items; i++)
                    if (k.m_item[i] != NULL && (int)(u8)k.m_item[i]->m_ID == s.a)
                        have = true;

                if (have && s.b == 0 && s.a == 102)
                {
                    SOCOM_PORT_TRACE("HOOK: f%d M40A1 is in the kit (armory)", frame);
                    break;
                }

                bool ok = k.SetItem((unsigned int)s.b, (EQUIP_ITEM)s.a);
                bool ammo = ok && k.SetItemAmmo((unsigned int)s.b, NULL);
                SOCOM_PORT_TRACE("HOOK: f%d TEST set slot %d = id %d (%s): %d ammo %d -> %s", frame, s.b, s.a, s.why, (int)ok, (int)ammo,
                    itemname(k.m_item[s.b]));

                if (s.b == 0)
                    k.SetCurItemByIndex(0);
                break;
            }
            case K_NIGHT:
                zdb::CWorld::m_world->m_night_mission = s.a;
                SOCOM_PORT_TRACE("HOOK: f%d %s", frame, s.why);
                break;
            case K_CAMX:
            {
                /* the camera beside the player looking 120 ahead (where the throw lands) */
                const CMatrix &pm = body->m_node->m_matrix;
                CPnt3D p = *body->GetPosW();
                CPnt3D target(p.x - pm.m_matrix[2][0] * 120.0f, p.y, p.z - pm.m_matrix[2][2] * 120.0f);
                CPnt3D eye(p.x + pm.m_matrix[0][0] * 60.0f + pm.m_matrix[2][0] * 20.0f, p.y + 40.0f,
                    p.z + pm.m_matrix[0][2] * 60.0f + pm.m_matrix[2][2] * 20.0f);
                freecam_look(eye, target);
                SOCOM_PORT_TRACE("HOOK: f%d test camera on the throw", frame);
                break;
            }
            case K_CAMOFF:
                freecam_off();
                break;
            case K_WALL:
            {
                const char *mname = "-";

                if (find_wall(body, g_wallpos, g_wallnorm, &mname))
                {
                    CPnt3D n(g_wallnorm.x, 0.0f, g_wallnorm.z);
                    float l = sqrtf(n.x * n.x + n.z * n.z);
                    n.x /= l; n.z /= l;
                    g_wallnorm = n;
                    CPnt3D target(g_wallpos.x + n.x * (float)s.a, g_wallpos.y, g_wallpos.z + n.z * (float)s.a);
                    put_seal(body, target, CPnt3D(-n.x, 0.0f, -n.z));
                    CPnt3D p = *body->GetPosW();
                    SOCOM_PORT_TRACE("HOOK: f%d TEST wall %s at %.1f %.1f %.1f normal %.2f %.2f: player put at %.1f %.1f %.1f facing it",
                        frame, mname, g_wallpos.x, g_wallpos.y, g_wallpos.z, n.x, n.z, p.x, p.y, p.z);
                }
                else
                    SOCOM_PORT_TRACE("HOOK: f%d no wall found", frame);
                break;
            }
            case K_ENEMY:
            {
                /* the nearest living enemy not used yet: a = 0 beside the wall spot, 1 ten in
                 * front of the player */
                CPnt3D me = *body->GetPosW();
                CZSealBody *best = s.b == 1 ? g_enemy : NULL;
                float bd = 1e30f;

                for (int i = 0; i < g_nseals && s.b != 1; i++)
                {
                    CZSealBody *e = g_seals[i];
                    bool used = false;

                    for (int j = 0; j < g_nused; j++)
                        used = used || g_used_enemy[j] == i;

                    CPnt3D q = *e->GetPosW();
                    float d = (q.x - me.x) * (q.x - me.x) + (q.z - me.z) * (q.z - me.z);

                    if (!used && (e->m_team & body->m_team) == 0 && e->m_isAlive && d < bd)
                    {
                        bd = d;
                        best = e;
                        g_used_enemy[g_nused < 4 ? g_nused : 3] = i;
                    }
                }

                if (best == NULL)
                    break;

                if (s.b != 1)
                    g_nused++;

                g_enemy = best;
                const CMatrix &pm = body->m_node->m_matrix;
                CPnt3D target;

                if (s.a == 0)
                    target = CPnt3D(g_wallpos.x + g_wallnorm.x * 5.0f + g_wallnorm.z * 7.0f, g_wallpos.y,
                        g_wallpos.z + g_wallnorm.z * 5.0f - g_wallnorm.x * 7.0f);
                else
                    target = CPnt3D(me.x - pm.m_matrix[2][0] * 14.0f, me.y, me.z - pm.m_matrix[2][2] * 14.0f);

                put_seal(best, target, CPnt3D(pm.m_matrix[2][0], 0.0f, pm.m_matrix[2][2]));
                CPnt3D q = *best->GetPosW();
                SOCOM_PORT_TRACE("HOOK: f%d TEST enemy %s put at %.1f %.1f %.1f (health %.2f)", frame, nm(best), q.x, q.y, q.z, best->m_health);
                break;
            }
            case K_CAMEXPL:
            {
                std::vector<CZProjectile*> &ex = CZWeapon::m_pProjectilelist->m_explosives;

                if (ex.empty())
                {
                    SOCOM_PORT_TRACE("HOOK: f%d no placed explosive", frame);
                    break;
                }

                CZProjectile *e = ex.back();
                CPnt3D c = e->m_framestartpos;
                CPnt3D p = *body->GetPosW();
                float dx = p.x - c.x, dz = p.z - c.z;
                float l = sqrtf(dx * dx + dz * dz);

                if (l < 1.0f) { dx = 1.0f; dz = 0.0f; l = 1.0f; }

                CPnt3D eye(c.x + dx / l * 45.0f - dz / l * 20.0f, c.y + 20.0f, c.z + dz / l * 45.0f + dx / l * 20.0f);
                freecam_look(eye, c);
                SOCOM_PORT_TRACE("HOOK: f%d camera on the placed %s at %.1f %.1f %.1f (instance active %d)", frame,
                    e->m_weapon != NULL && e->m_weapon->m_name != NULL ? e->m_weapon->m_name : "-", c.x, c.y, c.z,
                    e->m_instance != NULL ? (int)e->m_instance->m_active : -1);
                break;
            }
            case K_ENEMYTRACE:
                if (g_enemy != NULL)
                {
                    CPnt3D q = *g_enemy->GetPosW();
                    SOCOM_PORT_TRACE("HOOK: f%d %s: %s at %.1f %.1f %.1f health %.2f alive %d state %d", frame, s.why, nm(g_enemy), q.x, q.y, q.z,
                        g_enemy->m_health, (int)g_enemy->m_isAlive, (int)g_enemy->m_state);
                }
                break;
            default:
                break;
            }
        }

        if (frame % 300 == 0)
            trace(body, frame, "periodic");
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
