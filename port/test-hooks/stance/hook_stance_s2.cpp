/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-stance.
 * Wraps scePadRead: the hook presses buttons / holds the left stick itself (g_press / g_stick).
 * Wraps CameraZoom::AttachSeal: seal census (team-mates), player invincible.
 * Wraps CZSealBody::GetTerrainMotionFactor (per seal frame) for the player script:
 *  crouch (TRIANGLE), crouch walk, prone (TRIANGLE), crawl, stand (TRIANGLE), prone by double click,
 *  stand, run, zoom in to the scope (UP), hold still (heartbeat / wander decay), zoom out.
 *  Traces the player and the team-mates (state, wanted state, AI stance) every 30 frames.
 * Wraps CTStance::Begin (ai::STANCE): traces the seal and its stance.
 * Test camera (hook_freecam.h) from the side while crouch walking / crawling. */
#include <map>
#include <string>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include <string.h>
#include <math.h>
#include <libvu0.h>
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);
extern "C" void __real__ZN8CTStance5BeginEP14_zanim_cmd_hdr(_zanim_cmd_hdr *hdr);

namespace
{
CZSealBody *g_seals[64];
int g_nseals;
unsigned short g_press;   /* buttons (rdata[2] << 8 | rdata[3] bits) held for g_press_left reads */
int g_press_left;
int g_press2_at = -1;     /* second press of a double click after this many reads */
int g_stick_left;         /* left stick fully up for this many reads */
unsigned int g_reads;

const unsigned short B_TRIANGLE = 0x0010;
const unsigned short B_UP = 0x1000;
const unsigned short B_DOWN = 0x4000;

void press(unsigned short bits, const char *why, int frame)
{
    g_press = bits;
    g_press_left = 3;
    g_press2_at = -1;
    SOCOM_PORT_TRACE("HOOK: f%d press %04x (%s) at read %u", frame, bits, why, g_reads);
}

void dclick(unsigned short bits, const char *why, int frame)
{
    g_press = bits;
    g_press_left = 3;
    g_press2_at = 4; /* released 3 reads, pressed again: well inside 0.25 s */
    SOCOM_PORT_TRACE("HOOK: f%d double click %04x (%s) at read %u", frame, bits, why, g_reads);
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

const char *nm(CZSealBody *s)
{
    return s != NULL && s->m_node != NULL && s->m_node->m_name != NULL ? s->m_node->m_name : "-";
}

CPnt3D g_last;

void trace(CZSealBody *body, int frame, int phase)
{
    CPnt3D me = *body->GetPosW();
    float dx = me.x - g_last.x, dz = me.z - g_last.z;
    g_last = me;
    const float (&cm)[4][4] = zdb::CWorld::m_world->m_camera->m_matrix.m_matrix;
    CAiDecay *adr = body->m_adrenaline;
    SOCOM_PORT_TRACE("HOOK: f%d p%d me %.1f %.1f %.1f moved %.1f st %d want %d anim %d blends %d top %d/%d vel %.1f cam y %.1f (+%.1f) zoom %d adr %.3f hb %d",
        frame, phase, me.x, me.y, me.z, sqrtf(dx * dx + dz * dz), (int)body->m_state, (int)body->m_desiredState,
        (int)(s16)body->m_CurrentBlendAnimType, (int)body->m_blends->m_top + 1, (int)(s16)body->m_blends->Top()->m_animType,
        (int)body->m_blends->Top()->m_state,
        sqrtf(body->m_velM.x * body->m_velM.x + body->m_velM.y * body->m_velM.y + body->m_velM.z * body->m_velM.z),
        cm[3][1], cm[3][1] - me.y, (int)body->m_zoomstate, adr != NULL ? adr->m_value : -1.0f,
        (int)CZSealBody::m_heartbeat_curindex);

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];

        if (s == body || (s->m_team & body->m_team) == 0 || !s->m_isAlive)
            continue;

        CPnt3D p = *s->GetPosW();
        CSealCtrl *c = static_cast<CSealCtrl *>(s->m_control);
        CSealCtrlAi *ai = c != NULL ? c->GetSealCtrlAi() : NULL;
        SOCOM_PORT_TRACE("HOOK:   mate %s st %d want %d anim %d ai stance %d goal %d dist %.0f",
            nm(s), (int)s->m_state, (int)s->m_desiredState, (int)(s16)s->m_CurrentBlendAnimType,
            ai != NULL ? (int)ai->m_stance : -9, ai != NULL ? (int)ai->m_stance_goal : -9,
            sqrtf((p.x - me.x) * (p.x - me.x) + (p.z - me.z) * (p.z - me.z)));
    }
}

/* the nearest living team-mate (for the side camera) */
CZSealBody *mate(CZSealBody *body)
{
    CZSealBody *best = NULL;
    float bd = 1e30f;
    CPnt3D me = *body->GetPosW();

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];

        if (s == body || (s->m_team & body->m_team) == 0 || !s->m_isAlive)
            continue;

        CPnt3D p = *s->GetPosW();
        float d = (p.x - me.x) * (p.x - me.x) + (p.z - me.z) * (p.z - me.z);

        if (d < bd)
        {
            bd = d;
            best = s;
        }
    }

    return best;
}

void side_camera(CZSealBody *body)
{
    const CMatrix &pm = body->m_node->m_matrix;
    CPnt3D p = *body->GetPosW();
    CZSealBody *m = mate(body);
    CPnt3D target(p.x, p.y + 3.0f, p.z);

    if (m != NULL)
    {
        CPnt3D q = *m->GetPosW();

        if ((q.x - p.x) * (q.x - p.x) + (q.z - p.z) * (q.z - p.z) < 60.0f * 60.0f)
            target = CPnt3D((p.x + q.x) * 0.5f, p.y + 3.0f, (p.z + q.z) * 0.5f);
    }

    CPnt3D eye(target.x + pm.m_matrix[0][0] * 45.0f - pm.m_matrix[2][0] * 15.0f, target.y + 10.0f,
        target.z + pm.m_matrix[0][2] * 45.0f - pm.m_matrix[2][2] * 15.0f);
    freecam_look(eye, target);
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
            rdata[2] = (unsigned char)~(held >> 8);
            rdata[3] = (unsigned char)~held;
            g_press_left--;
        }
        else if (g_press2_at > 0)
        {
            if (--g_press2_at == 0)
                g_press_left = 3;
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

    if (player == NULL || world == NULL)
        return;

    g_nseals = 0;
    walk(world, 0);
    player->m_invincible = 1;
    SOCOM_PORT_TRACE("HOOK: census %d seals, player %s team 0x%x (invincible)", g_nseals, nm(player), player->m_team);

    for (int i = 0; i < g_nseals; i++)
        if (g_seals[i] != player && (g_seals[i]->m_team & player->m_team) != 0)
            SOCOM_PORT_TRACE("HOOK:   team-mate %s", nm(g_seals[i]));
}

extern "C" void __wrap__ZN8CTStance5BeginEP14_zanim_cmd_hdr(_zanim_cmd_hdr *hdr)
{
    __real__ZN8CTStance5BeginEP14_zanim_cmd_hdr(hdr);
    s32 *w = reinterpret_cast<s32 *>(hdr);
    SOCOM_PORT_TRACE("HOOK: ai::STANCE begin: peek %d stance %d delay %.2f", (int)w[2], (int)w[3], (double)*reinterpret_cast<f32 *>(&w[4]));
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer())
    {
        static int frame = 0;
        static int phase = 0;
        static int at = 0;
        static int tries = 0;
        frame++;
        s8 st = body->m_state;

        switch (phase)
        {
        case 0:
            if (frame == 120)
            {
                trace(body, frame, phase);
                press(B_TRIANGLE, "crouch", frame);
                phase = 1;
                at = frame;
            }
            break;
        case 1: /* crouched: walk */
            if (st == 1 && frame >= at + 90)
            {
                trace(body, frame, phase);
                SOCOM_PORT_TRACE("HOOK: f%d CROUCHED: crouch walk 90 reads", frame);
                g_stick_left = 90;
                phase = 2;
                at = frame;
            }
            else if (frame == at + 400)
            {
                SOCOM_PORT_TRACE("HOOK: f%d crouch did not happen", frame);
                phase = 2;
            }
            break;
        case 2:
            if (g_stick_left == 0 && frame >= at + 150)
            {
                trace(body, frame, phase);
                press(B_TRIANGLE, "prone", frame);
                phase = 3;
                at = frame;
            }
            break;
        case 3: /* prone: crawl */
            if (st == 2 && frame >= at + 120)
            {
                trace(body, frame, phase);
                SOCOM_PORT_TRACE("HOOK: f%d PRONE: crawl 150 reads", frame);
                g_stick_left = 150;
                phase = 4;
                at = frame;
            }
            else if (frame == at + 400)
            {
                SOCOM_PORT_TRACE("HOOK: f%d prone did not happen", frame);
                phase = 4;
            }
            break;
        case 4:
            if (g_stick_left == 0 && frame >= at + 240)
            {
                trace(body, frame, phase);
                press(B_TRIANGLE, "stand", frame);
                phase = 5;
                at = frame;
            }
            break;
        case 5:
            if (st == 0 && frame >= at + 90)
            {
                trace(body, frame, phase);
                dclick(B_TRIANGLE, "stand -> prone", frame);
                phase = 6;
                at = frame;
            }
            else if (frame == at + 400)
            {
                SOCOM_PORT_TRACE("HOOK: f%d stand did not happen", frame);
                phase = 6;
            }
            break;
        case 6:
            if ((st == 2 && frame >= at + 150) || frame == at + 400)
            {
                trace(body, frame, phase);
                press(B_TRIANGLE, "stand again", frame);
                phase = 7;
                at = frame;
            }
            break;
        case 7: /* run, then zoom in */
            if (frame == at + 120)
            {
                trace(body, frame, phase);
                SOCOM_PORT_TRACE("HOOK: f%d run 150 reads", frame);
                g_stick_left = 150;
            }
            else if (frame > at + 120 && g_stick_left == 0)
            {
                trace(body, frame, phase);
                press(B_UP, "zoom in", frame);
                phase = 8;
                at = frame;
                tries = 1;
            }
            break;
        case 8:
            if (body->m_kit.IsUsingScope())
            {
                trace(body, frame, phase);
                SOCOM_PORT_TRACE("HOOK: f%d SCOPED (zoom %d): hold still 900 frames", frame, (int)body->m_zoomstate);
                phase = 9;
                at = frame;
            }
            else if (frame == at + 20 && tries < 4)
            {
                press(B_UP, "zoom in more", frame);
                at = frame;
                tries++;
            }
            else if (frame == at + 40)
            {
                SOCOM_PORT_TRACE("HOOK: f%d no scope (zoom %d)", frame, (int)body->m_zoomstate);
                phase = 9;
                at = frame;
            }
            break;
        case 9:
            if (frame == at + 900)
            {
                trace(body, frame, phase);
                press(B_DOWN, "zoom out", frame);
                phase = 10;
                at = frame;
                tries = 1;
            }
            break;
        case 10:
            if ((s8)body->m_zoomstate > 0 && frame == at + 20 && tries < 5)
            {
                press(B_DOWN, "zoom out more", frame);
                at = frame;
                tries++;
            }
            else if ((s8)body->m_zoomstate <= 0 && frame >= at + 20)
            {
                trace(body, frame, phase);
                SOCOM_PORT_TRACE("HOOK: f%d back in third person; idle", frame);
                phase = 11;
                at = frame;
            }
            break;
        default:
            break;
        }

        /* test camera from the side while crouch walking and crawling */
        if ((phase == 2 && frame < at + 140) || (phase == 4 && frame < at + 220))
            side_camera(body);
        else if (g_freecam.on)
            freecam_off();

        if (phase >= 1 && phase <= 7 && frame % 30 == 0)
            trace(body, frame, phase);
        else if (frame % 300 == 0)
            trace(body, frame, phase);
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
