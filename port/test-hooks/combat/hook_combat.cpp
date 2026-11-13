/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-enemyai2, enemy combat behaviour in m8.
 * Wraps scePadRead (SELECT skips the mission cameras: hook_skipcams.h; R1 pulses for the fire test),
 * CameraZoom::AttachSeal (census; player invincible), CZSealBody::GetTerrainMotionFactor (player
 * frames after the cameras) for timed tests, each watched by the test camera (hook_freecam.h):
 *   fire  (SOCOM_HOOK_FIRE_AT): the awake enemy nearest the player is E; the player is put 80
 *         behind E (12 to its side) facing past E's side and fires R1 pulses for 120 frames, so
 *         the rounds pass E within thip_range while E does not see him (STATE_SHOTAT: cover).
 *   rush  (SOCOM_HOOK_RUSH_AT): unless a RUSH was seen, the next awake enemy gets STATE_RUSH at the
 *         player pushed and set up as CTState::Tick does (ai::STATE 29, "player").
 *   surr  (SOCOM_HOOK_SURR_AT): another awake enemy is asked for a reaction {0, 0, 0, 1}
 *         (SetDoReaction, as CAiSFlee does) -> DoReaction -> STATE_SURRENDER.
 *   flee  (SOCOM_HOOK_FLEE_AT): another one {0, 0, 1, 0} -> STATE_FLEE.
 * Every 10 frames during a test the tested AI; every 30 frames every enemy whose top state is not
 * SCRIPT / UNKNOWN (the combat states), and the player's ammo. */
#include <map>
#include <string>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zAI/zai.h"
#include "gamez/zWeapon/zweapon.h"
#include <string.h>
#include <math.h>
#include <libvu0.h>
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"
#include "hook_skipcams.h"

#ifndef SOCOM_HOOK_FIRE_AT
#define SOCOM_HOOK_FIRE_AT 60
#endif
#ifndef SOCOM_HOOK_RUSH_AT
#define SOCOM_HOOK_RUSH_AT 700
#endif
#ifndef SOCOM_HOOK_SURR_AT
#define SOCOM_HOOK_SURR_AT 1300
#endif
#ifndef SOCOM_HOOK_FLEE_AT
#define SOCOM_HOOK_FLEE_AT 1800
#endif
#ifndef SOCOM_HOOK_GREN_AT
#define SOCOM_HOOK_GREN_AT 1000
#endif
#ifndef SOCOM_HOOK_TEST_LEN
#define SOCOM_HOOK_TEST_LEN 450
#endif

extern "C" void __real__ZN10CameraZoom10AttachSealEP10CZSealBody(CZSealBody *seal);
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

namespace
{
CZSealBody *g_seals[64];
int g_nseals;
unsigned int g_reads;
int g_fire_left;          /* R1 pulses for this many reads */
CZSealBody *g_e[4];       /* the tested enemies (fire, rush, surr, flee) */
bool g_rush_seen;
CPnt3D g_fire_from;

const unsigned short B_R1 = 0x0008;

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

void place(CZSealBody *seal, const CPnt3D &at, const CPnt3D &face)
{
    zdb::CWorld *world = zdb::CWorld::m_world;
    CPnt3D target = at;
    CPnt3D probe(at.x, at.y + 60.0f, at.z);
    bool was = seal->m_node->SetActive(false);
    zdb::IntersectStruct *ground = world->GetAltitude(&probe, 100000.0f);
    seal->m_node->SetActive(was);

    if (ground != NULL)
        target.y = ground->m_pos.y;

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

    seal->TeleportTo(&target, &turn);
    seal->m_get_new_altitude = 1;
}

CSealCtrlAi *ai_of(CZSealBody *s)
{
    return s != NULL && s->m_control != NULL ? static_cast<CSealCtrl *>(s->m_control)->GetSealCtrlAi() : NULL;
}

const char *nm(CZSealBody *s)
{
    return s != NULL && s->m_node != NULL && s->m_node->m_name != NULL ? s->m_node->m_name : "-";
}

void trace_ai(int frame, CZSealBody *s, const char *tag)
{
    CSealCtrlAi *ai = ai_of(s);

    if (ai == NULL)
        return;

    CAiState *st = ai->GetAiState();
    CEntity *te = ai->m_target.m_target.m_ent;
    SOCOM_PORT_TRACE("HOOK: f%d %s %s at %.0f %.0f %.0f (%d,%d) alive %d state %d phase %d depth %d aware %d mode %d path %d/%d stance %d anim %d under %.2f threat %.2f courage %.2f target %s vis %d team 0x%x restr %d",
        frame, tag, nm(s), s->GetPosW()->x, s->GetPosW()->y, s->GetPosW()->z, s->m_mapLocValid.x, s->m_mapLocValid.y,
        (int)s->m_isAlive, (int)st->m_state, (int)st->m_substate, (int)ai->m_stateStack.size(), (int)ai->GetAiAware(), (int)ai->m_mode, (int)ai->m_path.m_state,
        (int)ai->m_path.m_points.size(), (int)ai->m_stance, s->m_blends->Top() != NULL ? (int)s->m_blends->Top()->m_animType : -1,
        (double)ai->m_underfire.m_value, (double)ai->m_targetThreat.m_value, (double)ai->m_courage.m_value,
        te != NULL && te->m_node != NULL ? te->m_node->m_name : "-", (int)ai->m_target.m_target.m_visible, s->m_team, (int)s->m_restrainable);
}

bool is_enemy(CZSealBody *s, CZSealBody *player)
{
    return s != player && (s->m_team & player->m_team) == 0 && s->m_isAlive && ai_of(s) != NULL && !ai_of(s)->m_sleeping && !ai_of(s)->m_snoozing;
}

bool used(CZSealBody *s)
{
    for (int i = 0; i < 4; i++)
        if (g_e[i] == s)
            return true;

    return false;
}

CZSealBody *nearest_enemy(CZSealBody *player)
{
    CPnt3D me = *player->GetPosW();
    CZSealBody *best = NULL;
    float bd = 1e30f;

    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];

        if (!is_enemy(s, player) || used(s))
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

void watch(CZSealBody *s)
{
    const CMatrix &m = s->m_node->m_matrix;
    /* from its right side and a little behind, 90 out, 45 up */
    freecam_node(s->m_node, m.m_matrix[0][0] * 90.0f + m.m_matrix[2][0] * 30.0f, 45.0f, m.m_matrix[0][2] * 90.0f + m.m_matrix[2][2] * 30.0f);
}

/* the fire test's aim: the player stays at g_fire_from and faces a point 12 to E's side */
void aim_player(CZSealBody *player, CZSealBody *e)
{
    const CMatrix &m = e->m_node->m_matrix;
    CPnt3D p = *e->GetPosW();
    CPnt3D side(m.m_matrix[0][0], 0.0f, m.m_matrix[0][2]);
    CPnt3D aim(p.x + side.x * 16.0f, p.y, p.z + side.z * 16.0f);
    place(player, g_fire_from, aim);
}

void census(int frame, CZSealBody *player)
{
    for (int i = 0; i < g_nseals; i++)
    {
        CZSealBody *s = g_seals[i];
        CSealCtrlAi *ai = ai_of(s);

        if (s == player || ai == NULL || (s->m_team & player->m_team) != 0 || !s->m_isAlive)
            continue;

        u8 t = ai->GetAiState()->m_state;

        if (t == STATE_RUSH)
            g_rush_seen = true;

        if (t != STATE_SCRIPT && t != STATE_UNKNOWN)
            trace_ai(frame, s, "combat");
    }

    CZKit *kit = &player->m_kit;
    CZFTSWeapon *w = kit->GetCurItem();
    SOCOM_PORT_TRACE("HOOK: f%d player at %.0f %.0f %.0f item %d mag %d ammo %d", frame, player->GetPosW()->x, player->GetPosW()->y, player->GetPosW()->z,
        (int)(u8)kit->GetCurItemEnum(), w != NULL ? (int)kit->CurMagHasAmmo() : -1, w != NULL ? (int)kit->CurItemHasAmmo() : -1);
}
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port == 0)
    {
        g_reads++;
        skipcams_pad(rdata);

        /* SELECT held across the camera's end opens the tactical map (the game pauses): close it
         * with TRIANGLE ("RESUME GAME") */
        {
            static unsigned int map_press;
            static int map_left;
            CZSealBody *pl = ftsGetPlayer();
            CSealCtrl *pc = pl != NULL && pl->m_control != NULL ? static_cast<CSealCtrl *>(pl->m_control) : NULL;

            if (pc != NULL && pc->m_menustate == stateFullScreenMapMenu && !skipcams_playing() && g_reads >= map_press + 60)
            {
                map_press = g_reads;
                map_left = 3;
                SOCOM_PORT_TRACE("HOOK: tactical map open at read %u: TRIANGLE closes it", g_reads);
            }

            if (map_left > 0)
            {
                rdata[3] &= (unsigned char)~0x10;
                map_left--;
            }
        }

        if (g_fire_left > 0)
        {
            /* R1 held 4 reads, released 4 */
            if ((g_fire_left & 7) >= 4)
                rdata[3] &= (unsigned char)~B_R1;

            g_fire_left--;
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
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    if (body == ftsGetPlayer() && !skipcams_busy())
    {
        static int frame = 0;
        frame++;

        if (frame % 30 == 0)
            census(frame, body);

        if (frame == 30)
        {
            for (int i = 0; i < g_nseals; i++)
            {
                CZSealBody *s = g_seals[i];
                char items[96];
                int n = 0;
                items[0] = 0;

                for (int k = 0; k < s->m_kit.GetNumItems() && n < 80; k++)
                {
                    CZFTSWeapon *w = s->m_kit.GetItemByIndex(k);
                    n += snprintf(items + n, sizeof(items) - n, " %d%s", w != NULL ? (int)(u8)w->m_ID : -1, s->m_kit.ItemHasAmmo(k) ? "" : "(0)");
                }

                SOCOM_PORT_TRACE("HOOK: kit %s team 0x%x sleeping %d:%s", nm(s), s->m_team, ai_of(s) != NULL ? (int)ai_of(s)->m_sleeping : -1, items);
            }
        }

        /* fire */
        if (frame == SOCOM_HOOK_FIRE_AT)
        {
            /* the nearest awake enemy that has a cover cell (not its own) from the shooting spot */
            CPnt3D me = *body->GetPosW();
            float bd = 1e30f;

            for (int i = 0; i < g_nseals; i++)
            {
                CZSealBody *s = g_seals[i];

                if (!is_enemy(s, body))
                    continue;

                CPnt3D sp = *s->GetPosW();
                CAiMapLoc here = s->m_mapLocValid, cover;
                CAiMap *map = AiMaps.GetMapByIndex(here.m_mapid);

                if (map == NULL)
                    continue;

                /* eight directions 80 out: a clear map line to E and a cover cell 2+ cells away */
                for (int k = 0; k < 8; k++)
                {
                    float a = (float)k * 0.785398f;
                    const CMatrix &sm = s->m_node->m_matrix;

                    /* behind E (out of its view): the direction against its facing */
                    if (-sm.m_matrix[2][0] * sinf(a) - sm.m_matrix[2][2] * cosf(a) > -0.3f)
                        continue;
                    CPnt3D from(sp.x + sinf(a) * 80.0f, sp.y + 20.0f, sp.z + cosf(a) * 80.0f);
                    CAiMapLoc fromloc;
                    CAiMap::DIR dir = (CAiMap::DIR)8;

                    if (!AiMaps.GetLocation(&from, fromloc) || !AiMaps.CanSeeLine(fromloc, here, NULL))
                        continue;

                    if (!map->FindCoverLoc(here, &from, cover, dir, 5))
                        continue;

                    int dx = (int)cover.x - (int)here.x, dy = (int)cover.y - (int)here.y;

                    if (dx * dx + dy * dy < 4)
                        continue;

                    CPnt3D me = *body->GetPosW();
                    float d = (sp.x - me.x) * (sp.x - me.x) + (sp.z - me.z) * (sp.z - me.z);
                    SOCOM_PORT_TRACE("HOOK: f%d %s at (%d,%d) has cover (%d,%d) from direction %d", frame, nm(s), here.x, here.y, cover.x, cover.y, k);

                    if (d < bd)
                    {
                        bd = d;
                        g_e[0] = s;
                        /* the player 12 to the side of that line */
                        g_fire_from = CPnt3D(from.x + cosf(a) * 12.0f, sp.y, from.z - sinf(a) * 12.0f);
                    }

                    break;
                }
            }

            if (g_e[0] == NULL)
                g_e[0] = nearest_enemy(body);

            if (g_e[0] != NULL)
            {
                CZSealBody *e = g_e[0];
                const CMatrix &m = e->m_node->m_matrix;
                CPnt3D p = *e->GetPosW();
                CPnt3D fwd(-m.m_matrix[2][0], 0.0f, -m.m_matrix[2][2]);
                CPnt3D side(m.m_matrix[0][0], 0.0f, m.m_matrix[0][2]);
                if (bd >= 1e30f)
                    g_fire_from = CPnt3D(p.x - fwd.x * 80.0f + side.x * 12.0f, p.y, p.z - fwd.z * 80.0f + side.z * 12.0f);
                aim_player(body, e);
                watch(e);
                g_fire_left = 0;
                SOCOM_PORT_TRACE("HOOK: f%d FIRE test: enemy %s at %.0f %.0f %.0f, player to %.0f %.0f %.0f", frame, nm(e), p.x, p.y, p.z, g_fire_from.x, g_fire_from.y, g_fire_from.z);
                trace_ai(frame, e, "fire");
            }
        }

        if (g_e[0] != NULL && frame > SOCOM_HOOK_FIRE_AT && frame < SOCOM_HOOK_FIRE_AT + SOCOM_HOOK_TEST_LEN)
        {
            CSealCtrlAi *ai = ai_of(g_e[0]);

            if (frame == SOCOM_HOOK_FIRE_AT + 20)
            {
                g_fire_left = 8 * 15;
                SOCOM_PORT_TRACE("HOOK: f%d R1 pulses (15) at read %u", frame, g_reads);
            }

            /* keep facing past E's side until it reacts (shot at, or sees the player) */
            if (frame < SOCOM_HOOK_FIRE_AT + 160 && g_e[0]->m_isAlive && ai->GetAiState()->m_state != STATE_SHOTAT && frame % 4 == 0)
                aim_player(body, g_e[0]);

            if (frame % 10 == 0)
                trace_ai(frame, g_e[0], "fire");
        }

        if (frame == SOCOM_HOOK_FIRE_AT + SOCOM_HOOK_TEST_LEN)
            freecam_off();

        /* rush */
        if (frame == SOCOM_HOOK_RUSH_AT)
        {
            g_e[1] = nearest_enemy(body);
            CSealCtrlAi *ai = ai_of(g_e[1]);
            SOCOM_PORT_TRACE("HOOK: f%d RUSH test: rush seen before %d, enemy %s", frame, (int)g_rush_seen, nm(g_e[1]));

            if (ai != NULL)
            {
                watch(g_e[1]);

                if (ai->PushAiState(STATE_RUSH, true))
                {
                    CAiSRush *rush = static_cast<CAiSRush *>(ai->GetAiState());
                    rush->m_time = 0.0f;
                    rush->m_option_flags &= ~3u;
                    rush->m_range_sq = 0.0f;
                    rush->SetTarget(body);
                    rush->m_setup = 1;
                    SOCOM_PORT_TRACE("HOOK: f%d %s RUSH pushed at the player", frame, nm(g_e[1]));
                }
                else
                {
                    SOCOM_PORT_TRACE("HOOK: f%d %s RUSH push refused (top %d)", frame, nm(g_e[1]), (int)ai->GetAiState()->m_state);
                }
            }
        }

        /* reload: the rush enemy's current magazine is emptied (it has more), as if fired out */
        if (frame == SOCOM_HOOK_RUSH_AT + 120 && g_e[1] != NULL && g_e[1]->m_isAlive)
        {
            CZKit &kit = g_e[1]->m_kit;
            int slot = kit.m_selected_item;

            if (slot >= 0 && slot < 30)
            {
                kit.m_reloads[slot][kit.m_currentmag[slot]] = 0;
                SOCOM_PORT_TRACE("HOOK: f%d %s magazine emptied (slot %d, mag %d; mag ammo %d, item ammo %d)", frame, nm(g_e[1]), slot,
                    kit.m_currentmag[slot], (int)kit.CurMagHasAmmo(), (int)kit.CurItemHasAmmo());
            }
        }

        if (g_e[1] != NULL && frame >= SOCOM_HOOK_RUSH_AT && frame < SOCOM_HOOK_RUSH_AT + SOCOM_HOOK_TEST_LEN && frame % 10 == 0)
            trace_ai(frame, g_e[1], "rush");

        if (frame == SOCOM_HOOK_RUSH_AT + SOCOM_HOOK_TEST_LEN)
            freecam_off();

        /* grenade: an enemy that sees the player and carries a thrown item takes it as a script's
         * ai::FIREMODE would (ChooseWeapon with the item's index); AttackTick then lobs it */
        static CZSealBody *gren;
        static int gren_at;

        if (gren == NULL && frame >= SOCOM_HOOK_GREN_AT && frame % 10 == 0)
        {
            for (int i = 0; i < g_nseals && gren == NULL; i++)
            {
                CZSealBody *s = g_seals[i];
                CSealCtrlAi *ai = ai_of(s);

                if (!is_enemy(s, body) || ai->m_target.m_target.m_ent != body || !ai->m_target.m_target.m_visible)
                    continue;

                for (int k = 0; k < s->m_kit.GetNumItems(); k++)
                {
                    CZFTSWeapon *w = s->m_kit.GetItemByIndex(k);
                    u8 id = w != NULL ? (u8)w->m_ID : 0;

                    if (id >= 120 && id < 126 && s->m_kit.ItemHasAmmo(k))
                    {
                        CAiWepHint hint;
                        memset(&hint, 0, sizeof(hint));
                        hint.m_use_index = 1;
                        hint.m_index = k;
                        ai->ChooseWeapon(hint);
                        gren = s;
                        gren_at = frame;
                        watch(s);
                        SOCOM_PORT_TRACE("HOOK: f%d GRENADE test: %s takes item %d (%d), player %.0f away", frame, nm(s), k, (int)id,
                            sqrtf(ai->m_target.m_target.m_distSq));
                        break;
                    }
                }
            }
        }

        if (gren != NULL && frame < gren_at + 300 && frame % 10 == 0)
            trace_ai(frame, gren, "gren");

        if (gren != NULL && frame == gren_at + 300)
            freecam_off();

        /* surrender / flee */
        for (int k = 0; k < 2; k++)
        {
            int at = k == 0 ? SOCOM_HOOK_SURR_AT : SOCOM_HOOK_FLEE_AT;
            CZSealBody *&e = g_e[2 + k];

            if (frame == at)
            {
                e = nearest_enemy(body);
                CSealCtrlAi *ai = ai_of(e);
                SOCOM_PORT_TRACE("HOOK: f%d %s test: enemy %s", frame, k == 0 ? "SURRENDER" : "FLEE", nm(e));

                if (ai != NULL)
                {
                    AI_REACTION r;
                    r.m_none = 0.0f;
                    r.m_rush = 0.0f;
                    r.m_flee = k == 1 ? 1.0f : 0.0f;
                    r.m_surrender = k == 0 ? 1.0f : 0.0f;
                    ai->SetDoReaction(true, r, true);
                    watch(e);
                }
            }

            if (e != NULL && frame >= at && frame < at + SOCOM_HOOK_TEST_LEN && frame % 10 == 0)
                trace_ai(frame, e, k == 0 ? "surr" : "flee");

            if (frame == at + SOCOM_HOOK_TEST_LEN)
                freecam_off();
        }
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}
