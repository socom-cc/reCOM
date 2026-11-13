/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-leftovers, part a (body carry).
 * Wraps CameraZoom::AttachSeal: the nearest enemy is put SOCOM_HOOK_KNIFE ahead of the player,
 * facing away (knife victim); the player is made invincible (stability run).
 * Wraps scePadRead: the hook presses buttons / holds the left stick itself (g_press / g_stick)
 * when the HUD offers what it waits for, so no read numbers have to be guessed.
 * Wraps CZSealBody::GetTerrainMotionFactor (per seal frame) for the player script:
 *  s0 knife offered (0x400) -> CROSS; s1 corpse offered for carry (0x100) -> CROSS (pickup);
 *  s2 carrying (state 9, pickup anims done) -> s3 stick forward SOCOM_HOOK_WALK reads, test camera
 *  from the side; s4 put down offered (0x200) -> CROSS; s5 put down (player crouched, body
 *  detached) -> s6 idle. Traces every 15 frames while busy, every 300 after. */
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

#ifndef SOCOM_HOOK_KNIFE
#define SOCOM_HOOK_KNIFE 12.0f
#endif
#ifndef SOCOM_HOOK_WALK
#define SOCOM_HOOK_WALK 90
#endif

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

namespace
{
CZSealBody *g_seals[64];
int g_nseals;
CZSealBody *g_victim;
unsigned short g_press;   /* buttons (rdata[2] << 8 | rdata[3] bits) held for g_press_left reads */
int g_press_left;
int g_left_at = -1;       /* while g_press_left == this .. -2: LEFT too (cycle the HUD action list) */
int g_stick_left;         /* left stick fully up for this many reads */
unsigned int g_reads;

void press(unsigned short bits, const char *why, int frame)
{
    g_press = bits;
    g_press_left = 3;
    g_left_at = -1;
    SOCOM_PORT_TRACE("HOOK: f%d press %04x (%s) at read %u", frame, bits, why, g_reads);
}

/* hold CROSS 12 reads and tap LEFT while held: the HUD's next action comes first, the release runs it */
void press_cycle(const char *why, int frame)
{
    g_press = 0x0040;
    g_press_left = 12;
    g_left_at = 8;
    SOCOM_PORT_TRACE("HOOK: f%d hold CROSS + LEFT (%s) at read %u", frame, why, g_reads);
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
}

const char *nm(CZSealBody *s)
{
    return s != NULL && s->m_node != NULL && s->m_node->m_name != NULL ? s->m_node->m_name : "-";
}

void trace(CZSealBody *body, int frame, int state)
{
    CSealCtrl *ctrl = static_cast<CSealCtrl *>(body->m_control);
    CPnt3D me = *body->GetPosW();
    CZSealBody *v = g_victim;
    CPnt3D vp = v != NULL ? *v->GetPosW() : CPnt3D(0.0f, 0.0f, 0.0f);
    SOCOM_PORT_TRACE("HOOK: f%d s%d me %.1f %.1f %.1f st %d anim %d blends %d carry %s | victim %s alive %d st %d anim %d at %.1f %.1f %.1f carry %s | victimbody %s corpse %s avail 0x%x sel 0x%x disp %d",
        frame, state, me.x, me.y, me.z, (int)body->m_state, (int)(s16)body->m_CurrentBlendAnimType, (int)body->m_blends->m_top + 1,
        nm(body->m_carry), nm(v), v != NULL ? (int)v->m_isAlive : -1, v != NULL ? (int)v->m_state : -1,
        v != NULL ? (int)(s16)v->m_CurrentBlendAnimType : -1, vp.x, vp.y, vp.z, v != NULL ? nm(v->m_carry) : "-",
        ctrl != NULL ? nm(ctrl->m_victimbody) : "-", ctrl != NULL ? nm(ctrl->m_corpsebody) : "-",
        body->ActionAvailableMask(), body->ActionSelectionMask(), (int)body->ActionDisplayOn());
}
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port == 0)
    {
        g_reads++;

        if (g_press_left > 0)
        {
            unsigned short held = (unsigned short)(~((rdata[2] << 8) | rdata[3]));
            held |= g_press;

            if (g_press_left <= g_left_at && g_press_left > g_left_at - 3)
                held |= 0x8000; /* LEFT */
            rdata[2] = (unsigned char)~(held >> 8);
            rdata[3] = (unsigned char)~held;
            g_press_left--;
        }

        if (g_stick_left > 0)
        {
            rdata[7] = 0; /* LY fully up: forward */
            g_stick_left--;
        }
    }

    return r;
}

extern "C" void __wrap__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal)
{
    __real__ZN10CameraZoom10AttachSealEP10CZSealBody(seal);
    CZSealBody *player = ftsGetPlayer();
    zdb::CWorld *world = zdb::CWorld::m_world;

    if (player == NULL || world == NULL || g_victim != NULL)
        return;

    g_nseals = 0;
    walk(world, 0);
    CPnt3D me = *player->GetPosW();
    const CMatrix &pm = player->m_node->m_matrix;
    CPnt3D fwd(-pm.m_matrix[2][0], 0.0f, -pm.m_matrix[2][2]);
    float fl = sqrtf(fwd.x * fwd.x + fwd.z * fwd.z);
    fwd.x /= fl; fwd.z /= fl;
    CZSealBody *victim = NULL;
    float dv = 1e30f;

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];
        CPnt3D p = *s->GetPosW();
        float d2 = (p.x - me.x) * (p.x - me.x) + (p.z - me.z) * (p.z - me.z);

        if (s != player && (s->m_team & player->m_team) == 0 && d2 < dv)
        {
            dv = d2;
            victim = s;
        }
    }

    player->m_invincible = 1;

    if (victim != NULL)
    {
        CPnt3D at(me.x + fwd.x * SOCOM_HOOK_KNIFE, me.y, me.z + fwd.z * SOCOM_HOOK_KNIFE);
        CPnt3D away(at.x + fwd.x * 100.0f, at.y, at.z + fwd.z * 100.0f);
#ifdef SOCOM_HOOK_CQB
        place(victim, at, me); /* facing the player: no knife, CQB first */
#else
        place(victim, at, away);
#endif
        g_victim = victim;
        SOCOM_PORT_TRACE("HOOK: knife victim %s to %.0f %.0f %.0f (player %.0f %.0f %.0f, invincible)", nm(victim), victim->GetPosW()->x,
            victim->GetPosW()->y, victim->GetPosW()->z, me.x, me.y, me.z);
    }
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer())
    {
        static int frame = 0;
        static int state = 0;
        static int at = 0;
        frame++;
        u32 avail = body->ActionAvailableMask();
        CSealCtrl *ctrl = static_cast<CSealCtrl *>(body->m_control);

#ifdef SOCOM_HOOK_CQB
        static int cqb_next = 0;

        if (state == 0 && g_victim != NULL && (avail & 0x1000) && frame > 30 && frame >= cqb_next)
        {
            trace(body, frame, state);

            if (body->ActionSelectionMask() == 0x1000)
                press(0x0040, "CQB", frame);
            else
                press_cycle("CQB not first", frame);

            cqb_next = frame + 60;
        }
        else if (state == 0 && g_victim != NULL && (s16)body->m_CurrentBlendAnimType == AnimTypes::CQB)
        {
            SOCOM_PORT_TRACE("HOOK: f%d CQB anim playing", frame);
            state = 10;
            at = frame;
        }
        else if (state == 10 && frame <= at + 450)
        {
            const CMatrix &pm = body->m_node->m_matrix;
            CPnt3D p = *body->GetPosW();
            CPnt3D target(p.x, p.y + 6.0f, p.z);
            CPnt3D eye(target.x + pm.m_matrix[0][0] * 30.0f - pm.m_matrix[2][0] * 12.0f, target.y + 8.0f,
                target.z + pm.m_matrix[0][2] * 30.0f - pm.m_matrix[2][2] * 12.0f);
            freecam_look(eye, target);

            if (frame % 15 == 0)
                trace(body, frame, state);

            if (frame == at + 450)
            {
                freecam_off();
                state = 11;
            }
        }
        else if (state == 11 && frame % 300 == 0)
        {
            trace(body, frame, state);
        }
        else
#endif
        if (state == 0 && g_victim != NULL && (avail & 0x400) && frame > 30)
        {
            trace(body, frame, state);
            press(0x0040, "knife", frame);
            state = 1;
            at = frame;
        }
        else if (state == 1 && at < 0 && body->m_carry != NULL)
        {
            trace(body, frame, state);
            SOCOM_PORT_TRACE("HOOK: f%d crouching to pick up %s", frame, nm(body->m_carry));
            state = 2;
            at = frame;
        }
        else if (state == 1 && ctrl != NULL && ctrl->m_corpsebody != NULL && (avail & 0x100))
        {
            static int next = 0;

            if (at >= 0)
            {
                trace(body, frame, state);
                SOCOM_PORT_TRACE("HOOK: f%d body carry offered (corpse %s), CROSS in 45 frames", frame, nm(ctrl->m_corpsebody));
                at = -frame;
                next = frame + 45;
            }
            else if (frame >= next && body->m_carry == NULL)
            {
                trace(body, frame, state);

                if (body->ActionSelectionMask() == 0x100)
                    press(0x0040, "carry", frame);
                else
                    press_cycle("carry not first", frame);

                next = frame + 60;
            }
            else if (body->m_carry != NULL)
            {
                state = 2;
                at = frame;
            }
        }
        else if (state == 1 && at > 0 && frame == at + 600)
        {
            trace(body, frame, state);
            CZSealBody *c = ctrl != NULL ? ctrl->m_corpsebody : NULL;
            SOCOM_PORT_TRACE("HOOK: f%d no carry offer: corpse %s can %d", frame, nm(c), c != NULL ? (int)body->CanUseBodyCarry(c) : -1);
        }
        else if (state == 2 && body->m_state == 9 && body->m_carry != NULL
            && (s16)body->m_CurrentBlendAnimType != AnimTypes::BuddyCarryPickup)
        {
            trace(body, frame, state);
            SOCOM_PORT_TRACE("HOOK: f%d carrying %s: walk forward %d reads", frame, nm(body->m_carry), SOCOM_HOOK_WALK);
            g_stick_left = SOCOM_HOOK_WALK;
            state = 3;
            at = frame;
        }
        else if (state == 2 && frame == at + 600)
        {
            trace(body, frame, state);
            SOCOM_PORT_TRACE("HOOK: f%d pickup did not finish", frame);
            state = 6;
        }
        else if (state == 3 && g_stick_left == 0)
        {
            trace(body, frame, state);
            state = 4;
            at = frame;
        }
        else if (state == 4 && frame >= at + 45 && (avail & 0x200))
        {
            trace(body, frame, state);
            press(0x0040, "put down", frame);
            state = 5;
            at = frame;
        }
        else if (state == 4 && frame == at + 400)
        {
            trace(body, frame, state);
            SOCOM_PORT_TRACE("HOOK: f%d put down not offered", frame);
            state = 6;
        }
        else if (state == 5 && frame >= at + 10 && body->m_carry == NULL && body->m_state != 9)
        {
            trace(body, frame, state);
            SOCOM_PORT_TRACE("HOOK: f%d put down done", frame);
            state = 6;
            at = frame;
        }

        /* crouched after the put down: a crouch walk forward (InStateCrouch / CrouchMoveControl) */
        if (state == 6 && frame == at + 150)
        {
            trace(body, frame, state);
            SOCOM_PORT_TRACE("HOOK: f%d crouch walk forward 45 reads", frame);
            g_stick_left = 45;
        }
        else if (state == 6 && frame > at + 150 && frame < at + 300 && frame % 15 == 0)
        {
            trace(body, frame, state);
        }

        /* test camera: from the side while carrying, until 120 frames after the put down */
        if (state >= 3 && state <= 5)
        {
            const CMatrix &pm = body->m_node->m_matrix;
            CPnt3D p = *body->GetPosW();
            CPnt3D target(p.x, p.y + 6.0f, p.z);
            CPnt3D eye(target.x + pm.m_matrix[0][0] * 28.0f - pm.m_matrix[2][0] * 10.0f, target.y + 6.0f,
                target.z + pm.m_matrix[0][2] * 28.0f - pm.m_matrix[2][2] * 10.0f);
            freecam_look(eye, target);
        }
        else if (state == 6 && frame == at + 120)
        {
            freecam_off();
        }

        if (state >= 1 && state <= 5 && frame % 15 == 0)
            trace(body, frame, state);
        else if (frame % 300 == 0)
            trace(body, frame, state);
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
