/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only). Wraps CameraZoom::AttachSeal: the nearest enemy is put
 * SOCOM_HOOK_ENEMY in front of the player (facing him). Wraps CZSealBody::GetTerrainMotionFactor
 * (per seal frame): for the player a small script once the enemy has dropped its weapon:
 *  1 the player is put SOCOM_HOOK_GAP from the dropped weapon, facing it (pad CROSS takes it);
 *  2 after the kit's slot 0 changes: 90 frames later 60 back (out of the ammo box's range),
 *    60 frames later back next to the box (the box is walked over again: ammo for the new gun);
 * and every 15 frames a trace of the pickups, the offered ids, the action masks and the kit. */
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
#include <math.h>
#include <libvu0.h>
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"
#include "hook_skipcams.h"

static int g_r1_left; /* socom-port-stance: R1 (fire) held for this many pad reads */
static int g_cross_left; /* socom-port-stance: CROSS held for this many pad reads */

#ifndef SOCOM_HOOK_ENEMY
#define SOCOM_HOOK_ENEMY 30.0f
#endif
#ifndef SOCOM_HOOK_GAP
#define SOCOM_HOOK_GAP 10.0f
#endif

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);

namespace
{
CZSealBody *g_seals[64];
int g_nseals;
CZSealBody *g_enemy;
CZSealBody *g_knife;

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

CQuat facing(const CPnt3D &at, const CPnt3D &face)
{
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

    return turn;
}

float ground(CZSealBody *seal, const CPnt3D &at)
{
    CPnt3D probe(at.x, at.y + 60.0f, at.z);
    bool was = seal->m_node->SetActive(false);
    zdb::IntersectStruct *g = zdb::CWorld::m_world->GetAltitude(&probe, 100000.0f);
    seal->m_node->SetActive(was);
    return g != NULL ? g->m_pos.y : at.y;
}

void place(CZSealBody *seal, const CPnt3D &at, const CPnt3D &face)
{
    CPnt3D target = at;
    target.y = ground(seal, at);
    CQuat turn = facing(target, face);
    seal->TeleportTo(&target, &turn);

    if (seal == ftsGetPlayer())
    {
        /* a standing seal keeps its last altitude hit: refresh it (boot-actions notes) */
        CPnt3D up = target;
        up.y += 11.0f;
        seal->m_alt = up.y;
        zdb::IntersectStruct *g = seal->SealGetAltitude(&up, 1.0f);

        if (g != NULL)
        {
            seal->m_last_altitude.m_pos = g->m_pos;
            seal->m_last_altitude.m_norm = g->m_norm;
            seal->m_last_altitude.m_poly = g->m_poly;
            seal->m_last_altitude.m_node = g->m_node;
            seal->m_alt = g->m_pos.y;
        }
    }
}

int g_flagcount[16];
int g_nflag2;

void census(zdb::CNode *node, int depth)
{
    if (node == NULL || depth > 40)
        return;

    for (zdb::CDIVector::iterator it = node->m_di.begin(); it != node->m_di.end(); ++it)
    {
        zdb::CDI *di = *it;

        if (di == NULL)
            continue;

        int f = di->m_appflags & 15;
        g_flagcount[f]++;

        if ((f == 1 || f == 2 || f == 3) && g_nflag2 < 12)
        {
            CMatrix m;
            sceVu0UnitMatrix(m.m_matrix);
            node->BuildMTW(m);
            SOCOM_PORT_TRACE("HOOK: DI flag %d on node %s at %.0f %.0f %.0f", f, node->m_name != NULL ? node->m_name : "-",
                m.m_matrix[3][0], m.m_matrix[3][1], m.m_matrix[3][2]);
            g_nflag2++;
        }
    }

    for (zdb::CNodeVector::iterator it = node->m_child.begin(); it != node->m_child.end(); ++it)
        census(*it, depth + 1);
}

void trace_kit(CZSealBody *body, const char *why)
{
    CZKit &kit = body->m_kit;
    char buf[400];
    int n = 0;
    buf[0] = 0;

    for (int i = 0; i < kit.m_num_items && i < 8 && n < 360; i++)
    {
        CZFTSWeapon *w = kit.m_item[i];
        int total = 0;

        for (int j = 0; j < 10; j++)
            total += kit.m_reloads[i][j];

        n += snprintf(buf + n, sizeof(buf) - n, " [%d %s mag %d rel %d ammo %s]", i, w != NULL ? w->GetName() : "-",
            kit.m_currentmag[i], total, kit.m_ammo[i] != NULL ? kit.m_ammo[i]->GetName() : "-");
    }

    SOCOM_PORT_TRACE("HOOK: kit (%s) sel %d items %d:%s", why, kit.m_selected_item, kit.m_num_items, buf);
}

void trace_pickups(CZSealBody *body)
{
    CPnt3D me = *body->GetPosW();

    for (std::list<CPickup *>::iterator it = CPickup::m_list.begin(); it != CPickup::m_list.end(); ++it)
    {
        CPickup *p = *it;
        CPnt3D *pos = p->GetPosW();
        float d = pos != NULL ? sqrtf((pos->x - me.x) * (pos->x - me.x) + (pos->y - me.y) * (pos->y - me.y) + (pos->z - me.z) * (pos->z - me.z)) : -1.0f;
        const char *what = "-";

        if (p->m_type == CPickup::PU_WEAPON && p->m_data != NULL)
            what = static_cast<CZFTSWeapon *>(p->m_data)->GetName();
        else if (p->m_type == CPickup::PU_AMMO && p->m_data != NULL)
        {
            static char ab[96];
            CZAmmoPickupInstance *box = static_cast<CZAmmoPickupInstance *>(p->m_data);
            int k = 0;
            ab[0] = 0;

            for (unsigned i = 0; i < box->m_ammo.size() && k < 80; i++)
                k += snprintf(ab + k, sizeof(ab) - k, "%s%s:%d", i ? "," : "", box->m_ammo[i] != NULL ? box->m_ammo[i]->GetName() : "-", box->m_counts[i]);

            what = ab;
        }

        SOCOM_PORT_TRACE("HOOK:   pickup %d type %d sec %d %s at %.1f %.1f %.1f dist %.1f node %s", (int)p->m_id, (int)p->m_type,
            (int)p->m_secondary, what, pos != NULL ? pos->x : 0.0f, pos != NULL ? pos->y : 0.0f, pos != NULL ? pos->z : 0.0f, d,
            p->m_node != NULL && p->m_node->m_name != NULL ? p->m_node->m_name : "-");
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
    CPnt3D me = *player->GetPosW();
    const CMatrix &pm = player->m_node->m_matrix;
    CPnt3D fwd(-pm.m_matrix[2][0], 0.0f, -pm.m_matrix[2][2]);
    float fl = sqrtf(fwd.x * fwd.x + fwd.z * fwd.z);
    fwd.x /= fl; fwd.z /= fl;
    CZSealBody *enemy = NULL;
    float de = 1e30f;

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];
        CPnt3D p = *s->GetPosW();
        float d2 = (p.x - me.x) * (p.x - me.x) + (p.z - me.z) * (p.z - me.z);

        if (s != player && (s->m_team & player->m_team) == 0 && d2 < de)
        {
            de = d2;
            enemy = s;
        }
    }

#ifdef SOCOM_HOOK_KNIFE
    /* the next nearest enemy SOCOM_HOOK_KNIFE ahead, facing away (knife victim) */
    CZSealBody *knife = NULL;
    float dk = 1e30f;

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];
        CPnt3D p = *s->GetPosW();
        float d2 = (p.x - me.x) * (p.x - me.x) + (p.z - me.z) * (p.z - me.z);

        if (s != player && s != enemy && (s->m_team & player->m_team) == 0 && d2 < dk)
        {
            dk = d2;
            knife = s;
        }
    }

    if (knife != NULL)
    {
        CPnt3D at(me.x + fwd.x * SOCOM_HOOK_KNIFE, me.y, me.z + fwd.z * SOCOM_HOOK_KNIFE);
        CPnt3D away(at.x + fwd.x * 100.0f, at.y, at.z + fwd.z * 100.0f);
        place(knife, at, away);
        g_knife = knife;
        SOCOM_PORT_TRACE("HOOK: knife victim %s to %.0f %.0f %.0f", knife->m_node->m_name, knife->GetPosW()->x, knife->GetPosW()->y, knife->GetPosW()->z);
    }
#endif

    g_enemy = enemy;
    trace_kit(player, "start");
    census(world, 0);
    SOCOM_PORT_TRACE("HOOK: DI app flags: 0:%d 1:%d 2:%d 3:%d 4:%d 5:%d 6:%d 7:%d 8+:%d", g_flagcount[0], g_flagcount[1], g_flagcount[2], g_flagcount[3], g_flagcount[4], g_flagcount[5], g_flagcount[6], g_flagcount[7], g_flagcount[8] + g_flagcount[9] + g_flagcount[10] + g_flagcount[11] + g_flagcount[12] + g_flagcount[13] + g_flagcount[14] + g_flagcount[15]);
    for (int i = 0; i < g_nseals; i++) if (g_seals[i] != player && (g_seals[i]->m_team & player->m_team) == 0 && i < 40) SOCOM_PORT_TRACE("HOOK: enemy %s team %x restrainable %d", g_seals[i]->m_node->m_name, g_seals[i]->m_team, (int)g_seals[i]->m_restrainable);

    if (enemy != NULL)
    {
        CPnt3D at(me.x + fwd.x * SOCOM_HOOK_ENEMY, me.y, me.z + fwd.z * SOCOM_HOOK_ENEMY);
        /* facing away from the player (he must not see him first) */
        CPnt3D away(at.x + fwd.x * 100.0f, at.y, at.z + fwd.z * 100.0f);
        place(enemy, at, away);
        SOCOM_PORT_TRACE("HOOK: enemy %s to %.0f %.0f %.0f", enemy->m_node->m_name, enemy->GetPosW()->x, enemy->GetPosW()->y, enemy->GetPosW()->z);
        trace_kit(enemy, "enemy");
    }
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer() && !skipcams_busy())
    {
        static int frame = 0;
        static int state = 0;
        static int at = 0;
        static CPnt3D box;
        static CZFTSWeapon *slot0 = NULL;
        frame++;
        CPnt3D me = *body->GetPosW();
        CSealCtrl *ctrl = static_cast<CSealCtrl *>(body->m_control);

        if (slot0 == NULL)
            slot0 = body->m_kit.m_item[0];

        static int dead_at = 0;
        static int knife_at = 0;

        if (g_knife != NULL && !g_knife->m_isAlive && knife_at == 0)
            knife_at = frame;

        if (knife_at != 0 && frame == knife_at + 180 && g_enemy != NULL && g_enemy->m_isAlive)
        {
            /* the shooting target SOCOM_HOOK_ENEMY in front of where the stab left the player, facing away */
            const CMatrix &pm = body->m_node->m_matrix;
            CPnt3D fwd(-pm.m_matrix[2][0], 0.0f, -pm.m_matrix[2][2]);
            float fl = sqrtf(fwd.x * fwd.x + fwd.z * fwd.z);
            fwd.x /= fl; fwd.z /= fl;
            CPnt3D at(me.x + fwd.x * SOCOM_HOOK_ENEMY, me.y, me.z + fwd.z * SOCOM_HOOK_ENEMY);
            CPnt3D away(at.x + fwd.x * 100.0f, at.y, at.z + fwd.z * 100.0f);
            place(g_enemy, at, away);
            SOCOM_PORT_TRACE("HOOK: f%d enemy %s placed again at %.0f %.0f %.0f", frame, g_enemy->m_node->m_name, g_enemy->GetPosW()->x, g_enemy->GetPosW()->y, g_enemy->GetPosW()->z);
        }

        if (state == 0 && g_enemy != NULL && !g_enemy->m_isAlive && dead_at == 0)
            dead_at = frame;

#ifdef SOCOM_HOOK_DROPCAM
        /* test camera: the dropped weapon from the side for 150 frames after the death */
        if (dead_at != 0 && frame == dead_at + 1)
        {
            CPickup *weapon = NULL;

            for (std::list<CPickup *>::iterator it = CPickup::m_list.begin(); it != CPickup::m_list.end(); ++it)
                if ((*it)->m_type == CPickup::PU_WEAPON && !(*it)->m_secondary)
                    weapon = *it;

            if (weapon != NULL && weapon->m_node != NULL)
            {
                const float *p = weapon->m_node->m_matrix.m_matrix[3];
                CPnt3D target(p[0], p[1] - 6.0f, p[2]);
                freecam_look_from(target, 30.0f, 4.0f, 30.0f);
                SOCOM_PORT_TRACE("HOOK: f%d test camera on the dropped weapon at %.1f %.1f %.1f", frame, p[0], p[1], p[2]);
            }
        }

        if (dead_at != 0 && frame == dead_at + 150)
            freecam_off();
#endif

        if (state == 0 && dead_at != 0 && frame >= dead_at + 90)
        {
            CPickup *weapon = NULL;

            for (std::list<CPickup *>::iterator it = CPickup::m_list.begin(); it != CPickup::m_list.end(); ++it)
            {
                if ((*it)->m_type == CPickup::PU_WEAPON && !(*it)->m_secondary)
                    weapon = *it; /* the latest: the shot enemy's */

                if ((*it)->m_type == CPickup::PU_AMMO)
                    box = *(*it)->GetPosW();
            }

            if (weapon != NULL && weapon->GetPosW() != NULL)
            {
                CPnt3D w = *weapon->GetPosW();
                CPnt3D d(me.x - w.x, 0.0f, me.z - w.z);
                float l = sqrtf(d.x * d.x + d.z * d.z);

                if (l > 0.01f)
                {
                    d.x /= l;
                    d.z /= l;
                }

                CPnt3D to(w.x + d.x * SOCOM_HOOK_GAP, me.y, w.z + d.z * SOCOM_HOOK_GAP);
                SOCOM_PORT_TRACE("HOOK: f%d enemy dead, weapon pickup %d at %.1f %.1f %.1f; player to %.1f %.1f", frame, (int)weapon->m_id,
                    w.x, w.y, w.z, to.x, to.z);
                trace_pickups(body);
                place(body, to, w);
                state = 1;
                at = frame;
            }
        }
        /* socom-port-stance: shoot the re-placed enemy (R1 6 reads every 40 frames) until it dies */
        if (state == 0 && frame == 90 && g_enemy != NULL && g_enemy->m_isAlive)
        {
            /* socom-port-stance: the enemy dies (body health 0 -> UpdateHealth: death anim, items dropped) */
            g_enemy->m_body_health = 0.0f;
            g_enemy->UpdateHealth((DAMAGE_LOCATION)3, (SEAL_DEATH_TYPE)1);
            SOCOM_PORT_TRACE("HOOK: f%d %s killed by the hook (alive %d)", frame, g_enemy->m_node->m_name, (int)g_enemy->m_isAlive);
        }

        if (state == 1 && frame == at + 45)
        {
            /* socom-port-stance: take the offered weapon (CROSS; the action runs on release) */
            SOCOM_PORT_TRACE("HOOK: f%d CROSS for the offered pickup %d", frame, ctrl != NULL ? ctrl->m_curpickup_ID : -9);
            g_cross_left = 4;
        }
        else if (state == 1 && body->m_kit.m_item[0] != slot0)
        {
            SOCOM_PORT_TRACE("HOOK: f%d slot 0 changed", frame);
            trace_kit(body, "taken");
            trace_pickups(body);
            state = 2;
            at = frame;
        }
        else if (state == 2 && frame == at + 90)
        {
            CPnt3D away(me.x + (me.x - box.x) * 0.0f + 60.0f, me.y, me.z);
            SOCOM_PORT_TRACE("HOOK: f%d player away from the ammo box", frame);
            place(body, away, box);
            state = 3;
            at = frame;
        }
        else if (state == 3 && frame == at + 60)
        {
            CPnt3D near(box.x + 6.0f, me.y, box.z);
            SOCOM_PORT_TRACE("HOOK: f%d player back to the ammo box %.1f %.1f", frame, box.x, box.z);
            place(body, near, box);
            state = 4;
            at = frame;
        }
        else if (state == 4 && frame == at + 60)
        {
            trace_kit(body, "after box");
            trace_pickups(body);
            state = 5;
        }

        if (state == 0 && frame % 15 == 0 && frame < 900 && g_enemy != NULL)
        {
            CPnt3D e = *g_enemy->GetPosW();
            CSealCtrl *ec = static_cast<CSealCtrl *>(g_enemy->m_control);
            CSealCtrlAi *ai = ec != NULL ? ec->GetSealCtrlAi() : NULL;
            SOCOM_PORT_TRACE("HOOK: f%d s0 pos %.1f %.1f %.1f enemy %.1f %.1f alive %d/%d aware %d victim %s corpse %s avail 0x%x sel 0x%x disp %d anim %d", frame, me.x, me.y, me.z, e.x, e.z, (int)g_enemy->m_isAlive, g_knife != NULL ? (int)g_knife->m_isAlive : -1,
                ai != NULL ? (int)ai->GetAiAware() : -1, ctrl != NULL && ctrl->m_victimbody != NULL ? ctrl->m_victimbody->m_node->m_name : "-",
                ctrl != NULL && ctrl->m_corpsebody != NULL ? ctrl->m_corpsebody->m_node->m_name : "-", body->ActionAvailableMask(), body->ActionSelectionMask(), (int)body->ActionDisplayOn(), (int)body->m_CurrentBlendAnimType);
        }

        if (state >= 1 && state <= 4 && frame % 15 == 0)
            SOCOM_PORT_TRACE("HOOK: f%d s%d pos %.1f %.1f %.1f offer %d/%d avail 0x%x sel 0x%x disp %d timer %.2f pickups %d", frame, state,
                me.x, me.y, me.z, ctrl != NULL ? ctrl->m_curpickup_ID : -9, ctrl != NULL ? ctrl->m_curpickup_secondary_ID : -9,
                body->ActionAvailableMask(), body->ActionSelectionMask(), (int)body->ActionDisplayOn(),
                ctrl != NULL ? ctrl->m_weapon_pickup_timer : 0.0f, (int)CPickup::m_list.size());

#ifdef SOCOM_HOOK_TAKECAM
        /* socom-port-stance: the player from the side while he is next to the weapon and takes it */
        if (state >= 1 && state <= 2 && !(state == 2 && frame > at + 80))
        {
            const CMatrix &pm = body->m_node->m_matrix;
            CPnt3D pp = *body->GetPosW();
            CPnt3D target(pp.x, pp.y + 5.0f, pp.z);
            CPnt3D eye(target.x + pm.m_matrix[0][0] * 26.0f - pm.m_matrix[2][0] * 14.0f, target.y + 5.0f,
                target.z + pm.m_matrix[0][2] * 26.0f - pm.m_matrix[2][2] * 14.0f);
            freecam_look(eye, target);

            if (frame % 5 == 0)
                SOCOM_PORT_TRACE("HOOK: f%d s%d take anim %d blends %d top %d/%d", frame, state, (int)(s16)body->m_CurrentBlendAnimType,
                    (int)body->m_blends->m_top + 1, (int)(s16)body->m_blends->Top()->m_animType, (int)body->m_blends->Top()->m_state);
        }
        else if (state == 2 && frame == at + 81)
        {
            freecam_off();
        }
#endif
    }


    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}

extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

/* hook.sh always wraps scePadRead (socom-port-leftovers); this hook leaves the pad to the fake pad */
extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port == 0)
        skipcams_pad(rdata);

    if (port == 0 && g_r1_left > 0)
    {
        rdata[3] &= (unsigned char)~0x08; /* R1 held (active low) */
        g_r1_left--;
    }

    if (port == 0 && g_cross_left > 0)
    {
        rdata[3] &= (unsigned char)~0x40; /* CROSS held (active low) */
        g_cross_left--;
    }

    return r;
}
