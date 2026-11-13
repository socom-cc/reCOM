/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): socom-port-missionwin - win m8 the mission's own way.
 * Wraps scePadRead (state-driven pad: movie skip, mission cameras skipped with SELECT, the tac
 * map, grenade throws, debrief X), CMission::OnMissionStart, CZSealBody::GetTerrainMotionFactor
 * (the script, run in the player's frame) and CheckDIShoot (test camera).
 * The script puts the player (invincible) where each objective's own trigger fires: the
 * InsertObj region, Bravo into Ambush, the sentry killed (real fall damage, the player the
 * killer), the laptop action executed, the lodge / Bosler / cabin guards killed and the player in
 * their search regions, the weapon crates blown with thrown M67s, Snow3 restrained (the
 * restraint action), escorted (CMD_ESCORT to the fireteam), moved into the Extract region.
 * Objective valves are never written: every change is traced as the game makes it. */
#include <map>
#include <string>
#include <vector>
#include <list>
#define protected public
#define private public
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zGame/zgame.h"
#include "gamez/zAI/zai.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zNode/node_action.h"
#include "gamez/zValve/zvalve.h"
#include "gamez/zWeapon/zweapon.h"
#include "gamez/zWeapon/zwep_projectilelist.h"
#include "Apps/FTS/state/state.h"
#include "Apps/FTS/hud/hud.h"
#include <string.h>
#include <math.h>
#include "hook_skipcams.h"
#ifndef SOCOM_HOOK_C4_GAP
#define SOCOM_HOOK_C4_GAP 6.0f
#endif
#ifndef SOCOM_HOOK_THROW_DIST
#define SOCOM_HOOK_THROW_DIST 40.0f
#endif
#ifndef SOCOM_HOOK_THROW_PRESSURE
#define SOCOM_HOOK_THROW_PRESSURE 0x33
#endif
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"

extern COurGame theGame;
extern "C" float __real__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body);
extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);
extern "C" void __real__ZN8CMission14OnMissionStartEv(CMission *mission);

namespace
{
enum { B_SELECT = 0x0100, B_START = 0x0800, B_UP = 0x1000, B_DOWN = 0x4000, B_R2 = 0x0002, B_R1 = 0x0008,
       B_TRIANGLE = 0x0010, B_CROSS = 0x0040 };

struct Press { unsigned int at, len; unsigned short bits; };
Press g_queue[256];
int g_nqueue;
unsigned int g_reads;
bool g_new_mission;
int g_mission;

void press(unsigned int at, unsigned short bits, unsigned int len = 3)
{
    if (g_nqueue < 256)
    {
        g_queue[g_nqueue].at = at;
        g_queue[g_nqueue].len = len;
        g_queue[g_nqueue].bits = bits;
        g_nqueue++;
    }
}

const void *top_state()
{
    const void *top = NULL;

    for (unsigned int i = 0; i < 16; i++)
        if (theGame.m_Stack[i] != NULL)
            top = theGame.m_Stack[i];

    return top;
}

const char *name_of(const void *s)
{
    if (s == &theGame.m_menuState) return "menu";
    if (s == &theGame.m_loadState) return "load";
    if (s == &theGame.m_coreState) return "core";
    if (s == &theGame.m_exitState) return "exit";
    if (s == &theGame.m_cinematicSubState) return "cinematic";
    return s != NULL ? "other" : "none";
}

/* ---- valves: every change of these is traced ---- */
const char *g_watch[] = { "POBJ1", "POBJ2", "POBJ3", "POBJ4", "POBJ5", "SOBJ1", "SOBJ2", "SOBJ3", "SOBJ4", "SOBJ6",
    "SOBJ7", "SOBJ9", "SOBJ10", "SOBJ10Fail", "SOBJ9Fail", "SOBJ9Display", "computer", "cratecount", "extract",
    "hostage", "aiteam_11", "Snow1_valve_alive", "Snow2_valve_alive", "Shed1_valve_alive", "OutPatrol4_valve_alive",
    "Snow3_valve_alive", "mission_complete", "mission_failure", "nofade", "player_valve_alive", "nodocs",
    "aiteam_01", "incr_miss_8", "GameComplete", "StatObjectivesPct", "StatsProgress", NULL };
int g_last[64];
bool g_watch_init;

void watch_valves()
{
    for (int i = 0; g_watch[i] != NULL; i++)
    {
        CValve *v = CValve::GetByName(g_watch[i]);
        int value = v != NULL ? (int)v->m_value : -999;

        if (!g_watch_init || value != g_last[i])
        {
            if (g_watch_init)
                SOCOM_PORT_TRACE("HOOK: read %u VALVE %s %d -> %d", g_reads, g_watch[i], g_last[i], value);
            g_last[i] = value;
        }
    }

    g_watch_init = true;
}

/* ---- places ---- */
CZSealBody *seal_named(const char *name)
{
    CEntity *e = CEntity::m_list.GetEntity(name);
    return e != NULL ? SealOfEntity(e) : NULL;
}

bool region_center(const char *name, CPnt3D &out, int *type = NULL)
{
    for (CAiMaps::iterator it = AiMaps.begin(); it != AiMaps.end(); ++it)
    {
        CAiMap *map = (CAiMap *)*it;

        for (CAiMap::regions::iterator r = map->m_regionTable.begin(); r != map->m_regionTable.end(); ++r)
        {
            if (strcmp(r->m_name, name) != 0)
                continue;

            CAiMapLoc loc = r->m_loc;
            loc.x = r->m_loc.x + r->m_dx / 2;
            loc.y = r->m_loc.y + r->m_dy / 2;
            map->GetCellPos(loc, out);

            if (type != NULL)
                *type = (int)r->m_type;

            return true;
        }
    }

    return false;
}

void list_regions()
{
    for (CAiMaps::iterator it = AiMaps.begin(); it != AiMaps.end(); ++it)
    {
        CAiMap *map = (CAiMap *)*it;

        for (CAiMap::regions::iterator r = map->m_regionTable.begin(); r != map->m_regionTable.end(); ++r)
        {
            CPnt3D c;
            region_center(r->m_name, c);
            SOCOM_PORT_TRACE("HOOK: region %s map %d type %d at %d,%d size %d x %d centre %.0f %.0f %.0f", r->m_name, map->m_mapid,
                (int)r->m_type, (int)r->m_loc.x, (int)r->m_loc.y, (int)r->m_dx, (int)r->m_dy, c.x, c.y, c.z);
        }
    }
}

CQuat facing(const CPnt3D &dir)
{
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

    return turn;
}

/* a seal onto the ground at (x, z), facing dir; the altitude hit refreshed (a standing seal
 * keeps its last one) */
void put(CZSealBody *seal, CPnt3D at, CPnt3D dir, const char *what)
{
    if (seal == NULL)
        return;

    float len = sqrtf(dir.x * dir.x + dir.z * dir.z);

    if (len < 0.01f) { dir = CPnt3D(0.0f, 0.0f, 1.0f); len = 1.0f; }

    dir.x /= len; dir.y = 0.0f; dir.z /= len;
    zdb::CNode *node = seal->m_node;
    bool was = node->SetActive(false);
    CPnt3D probe(at.x, at.y + 40.0f, at.z);
    float keep_alt = seal->m_alt;
    seal->m_alt = probe.y;
    zdb::IntersectStruct *ground = seal->SealGetAltitude(&probe, 1.0f);
    seal->m_alt = keep_alt;
    node->SetActive(was);
    at.y = ground != NULL ? ground->m_pos.y : at.y;
    CQuat turn = facing(dir);
    seal->TeleportTo(&at, &turn);
    CPnt3D a = at;
    a.y += 11.0f;
    seal->m_alt = a.y;
    zdb::IntersectStruct *g = seal->SealGetAltitude(&a, 1.0f);

    if (g != NULL)
    {
        seal->m_last_altitude.m_pos = g->m_pos;
        seal->m_last_altitude.m_norm = g->m_norm;
        seal->m_last_altitude.m_poly = g->m_poly;
        seal->m_last_altitude.m_node = g->m_node;
        seal->m_alt = g->m_pos.y;
    }

    SOCOM_PORT_TRACE("HOOK: read %u %s: %s to %.0f %.0f %.0f", g_reads, what, seal->m_node->m_name, at.x, at.y, at.z);
}

bool put_in_region(CZSealBody *seal, const char *region, float dx, float dz)
{
    CPnt3D c;

    if (!region_center(region, c))
    {
        SOCOM_PORT_TRACE("HOOK: region %s not found", region);
        return false;
    }

    c.x += dx;
    c.z += dz;
    put(seal, c, CPnt3D(0.0f, 0.0f, 1.0f), region);
    return true;
}

void kill(CZSealBody *seal, CZSealBody *by)
{
    if (seal == NULL || !seal->m_isAlive)
        return;

    seal->HandleKiller(by->m_id);
    int level = seal->HandleFallingDamage(300.0f);
    SOCOM_PORT_TRACE("HOOK: read %u kill %s (fall level %d, alive %d)", g_reads, seal->m_node->m_name, level, (int)seal->m_isAlive);
}

void kill_team(int team, CZSealBody *by)
{
    for (CEntityList::iterator it = CEntity::m_list.begin(); it != CEntity::m_list.end(); ++it)
    {
        CZSealBody *s = SealOfEntity(*it);

        if (s != NULL && s->m_isAlive && (s->m_team & (1u << team)) != 0 && (s->m_team & 0x20000) == 0)
            kill(s, by);
    }
}

/* the node's origin through its parents' local matrices (row vectors) */
CPnt3D chain_pos(zdb::CNode *node)
{
    float p[3] = { 0.0f, 0.0f, 0.0f };

    for (zdb::CNode *n = node; n != NULL; n = n->m_parent)
    {
        const float (*m)[4] = n->m_matrix.m_matrix;
        float q[3];

        for (int j = 0; j < 3; j++)
            q[j] = p[0] * m[0][j] + p[1] * m[1][j] + p[2] * m[2][j] + m[3][j];

        p[0] = q[0]; p[1] = q[1]; p[2] = q[2];
    }

    return CPnt3D(p[0], p[1], p[2]);
}

unsigned char g_r1_pressure = 0xff;

CPnt3D world_pos(zdb::CNode *node)
{
    CMatrix m;
    sceVu0UnitMatrix(m.m_matrix);
    node->BuildMTW(m);
    return CPnt3D(m.m_matrix[3][0], m.m_matrix[3][1], m.m_matrix[3][2]);
}

zdb::CNode *g_crates[8];
int g_ncrates;

void find_crates(zdb::CNode *node, int depth)
{
    if (node == NULL || depth > 12 || g_ncrates >= 8)
        return;

    if (node->m_name != NULL && strncmp(node->m_name, "crate_group", 11) == 0)
    {
        g_crates[g_ncrates++] = node;
        CPnt3D p = world_pos(node);
        SOCOM_PORT_TRACE("HOOK: crate %s at %.0f %.0f %.0f ex %p bbox %.0f %.0f %.0f .. %.0f %.0f %.0f", node->m_name, p.x, p.y, p.z,
            (void *)node->m_nodeEx, node->m_bbox.m_min.x, node->m_bbox.m_min.y, node->m_bbox.m_min.z, node->m_bbox.m_max.x,
            node->m_bbox.m_max.y, node->m_bbox.m_max.z);

        for (zdb::CNode *up = node->m_parent; up != NULL; up = up->m_parent)
            SOCOM_PORT_TRACE("HOOK:   parent %s local %.0f %.0f %.0f", up->m_name != NULL ? up->m_name : "-", up->m_matrix.m_matrix[3][0],
                up->m_matrix.m_matrix[3][1], up->m_matrix.m_matrix[3][2]);

        SOCOM_PORT_TRACE("HOOK:   own local %.0f %.0f %.0f", node->m_matrix.m_matrix[3][0], node->m_matrix.m_matrix[3][1], node->m_matrix.m_matrix[3][2]);
        CPnt3D w = chain_pos(node);
        SOCOM_PORT_TRACE("HOOK:   chain %.0f %.0f %.0f", w.x, w.y, w.z);
        return;
    }

    for (zdb::CNodeVector::iterator it = node->m_child.begin(); it != node->m_child.end(); ++it)
        find_crates(*it, depth + 1);
}

CNodeAction *action_named(const char *node_name)
{
    for (CNodeAction::Container::iterator it = CNodeAction::m_actions.begin(); it != CNodeAction::m_actions.end(); ++it)
        if ((*it)->m_node != NULL && strcmp((*it)->m_node->m_name, node_name) == 0)
            return *it;

    return NULL;
}

int val(const char *name)
{
    CValve *v = CValve::GetByName(name);
    return v != NULL ? (int)v->m_value : -999;
}

/* TEST STAND-IN for the unwritten C4 placement (CZKit::TickExplosives' placement branch, the
 * kit worker's): the M67s the player throws at the weapon crates carry the C4 ammo record
 * (explosion 18, radius 15.25) instead of the frag's (10 < the crates' shield 11). The crates'
 * WEAPON_HIT anims then run from the real blast (HandleDetonateExplosion -> CZAnimEx::OnWeaponHit). */
void c4_standin(CZSealBody *player)
{
    CZProjectileList *list = CZWeapon::m_pProjectilelist;
    CZAmmo *c4 = CZAmmo::m_ammolist.GetAmmo("C4 Ammo");

    if (list == NULL || list->m_projectiles == NULL || c4 == NULL)
        return;

    for (s32 i = 0; i <= list->m_lastused; i++)
    {
        CZProjectile *p = &list->m_projectiles[i];

        if (list->m_used[i] == 1 && p->m_owner == player->m_node && p->m_ammo != c4 && p->m_ammo != NULL
            && strcmp(p->m_ammo->GetName(), "Frag Grenade Ammo") == 0)
        {
            p->m_ammo = c4;
            SOCOM_PORT_TRACE("HOOK: read %u TEST STAND-IN: thrown M67 %d carries the C4 ammo", g_reads, (int)i);
        }
    }
}

/* the player's C4 projectiles in the list (placed ones; a new one = a placement) */
int c4_count(CZSealBody *player)
{
    int n = 0;

    CZProjectileList *list = CZWeapon::m_pProjectilelist;

    if (list == NULL || list->m_projectiles == NULL)
        return 0;

    for (s32 i = 0; i <= list->m_lastused; i++)
    {
        CZProjectile *p = &list->m_projectiles[i];

        if (list->m_used[i] == 1 && p->m_owner == player->m_node && p->m_ammo != NULL && strcmp(p->m_ammo->GetName(), "C4 Ammo") == 0)
            n++;
    }

    return n;
}

/* ---- the script ---- */
int g_step = -1;
int g_pause_row = -1;
unsigned int g_pause_from;
unsigned int g_pause_next;
unsigned int g_step_at;
int g_crate;
unsigned int g_next_throw;
int g_c4_side;
int g_c4_base;
unsigned int g_cam_off;
unsigned int g_map_at;

void next(int step)
{
    g_step = step;
    g_step_at = g_reads;
    SOCOM_PORT_TRACE("HOOK: read %u step %d", g_reads, step);
}

void open_map_soon(unsigned int after)
{
    /* the tac map: SELECT, the objective list with its checkboxes; closed 120 reads later */
    press(g_reads + after, B_SELECT);
    press(g_reads + after + 120, B_SELECT);
    g_map_at = g_reads + after;
}

void script(CZSealBody *player)
{
    unsigned int t = g_reads - g_step_at;
    CZSealBody *snow3 = seal_named("Snow3");

#ifdef SOCOM_HOOK_EXITPATHS
    /* regression of the exit paths (-DSOCOM_HOOK_EXITPATHS): mission 1 pause ABORT -> failure
     * debrief -> X (replay); mission 2 pause REPLAY; mission 3 pause ABORT -> debrief TRIANGLE ->
     * menus */
    if (g_step == 0 && !skipcams_busy())
    {
        int row = g_mission == 2 ? 3 : 1;
        SOCOM_PORT_TRACE("HOOK: read %u mission %d: pause, row %d", g_reads, g_mission, row);
        press(g_reads + 60, B_START);
        g_pause_row = row;
        g_pause_from = g_reads + 100;
        next(50);
    }

    return;
#endif

    switch (g_step)
    {
    case 0: /* cameras done: census, invincible, into InsertObj */
        if (skipcams_busy())
            return;

        list_regions();
        g_ncrates = 0;
        find_crates(zdb::CWorld::m_world, 0);
        player->m_invincible = 1;

        /* the SEALs too (66d011d: enemies rush and throw grenades; aiteam_01 == 1 fails the
         * mission) - test only */
        {
            const char *seals[3] = { "Bailey", "DiMone", "Hutchins" };

            for (int i = 0; i < 3; i++)
                if (seal_named(seals[i]) != NULL)
                    seal_named(seals[i])->m_invincible = 1;
        }
        put_in_region(player, "InsertObj", 0.0f, 0.0f);
        next(1);
        break;

    case 1: /* POBJ4 (Insert); Bravo into Ambush while the sentry lives (SOBJ10) */
        if (t == 30)
        {
            put_in_region(seal_named("Bailey"), "Ambush", -5.0f, 0.0f);
            put_in_region(seal_named("DiMone"), "Ambush", 5.0f, 0.0f);
        }

        if ((val("POBJ4") == 1 && val("SOBJ10") == 1) || t > 400)
        {
            open_map_soon(150);
            next(2);
        }
        break;

    case 2: /* the sentry (SOBJ1) */
        if (t == 300)
            kill(seal_named("OutPatrol4"), player);

        if ((t > 300 && val("SOBJ1") == 1) || t > 600)
            next(3);
        break;

    case 3: /* the laptop: its node action as the action button runs it (GetDocs: computer = 99);
             * the dredge's leader first (alerted, he erases the documents 60 s later: nodocs) */
        if (t == 1)
        {
            kill(seal_named("Leader"), player);

            CNodeAction *laptop = action_named("computer_action");

            if (laptop != NULL)
            {
                CPnt3D at = world_pos(laptop->m_node);
                put(player, CPnt3D(at.x, at.y, at.z + 10.0f), CPnt3D(0.0f, 0.0f, -1.0f), "laptop");
            }
            else
                SOCOM_PORT_TRACE("HOOK: no computer_action");
        }

        if (t == 40)
        {
            CNodeAction *laptop = action_named("computer_action");

            if (laptop != NULL)
            {
                bool ok = laptop->ExecuteAction(player, 0);
                SOCOM_PORT_TRACE("HOOK: read %u laptop ExecuteAction -> %d (valve %d)", g_reads, (int)ok,
                    laptop->m_valve != NULL ? (int)laptop->m_valve->m_value : -1);
            }
        }

        if ((t > 40 && val("POBJ1") == 1) || t > 900)
        {
            open_map_soon(200);
            next(4);
        }
        break;

    case 4: /* the lodge (SOBJ2): its guards (team 11), then the player in SearchLodge */
        if (t == 350)
            kill_team(11, player);

        if (t == 400)
            put_in_region(player, "SearchLodge", 0.0f, 0.0f);

        if ((t > 400 && val("SOBJ2") == 1) || t > 800)
            next(5);
        break;

    case 5: /* the Bosler house (SOBJ3) */
        if (t == 10)
        {
            kill(seal_named("Snow1"), player);
            kill(seal_named("Snow2"), player);
        }

        if (t == 60)
            put_in_region(player, "SearchSnow", 0.0f, 0.0f);

        if ((t > 60 && val("SOBJ3") == 1) || t > 400)
            next(6);
        break;

    case 6: /* the cabin (SOBJ4), then the compound (POBJ5) */
        if (t == 10)
            kill(seal_named("Shed1"), player);

        if (t == 60)
            put_in_region(player, "Safe1", 0.0f, 0.0f);

        if ((t > 60 && val("POBJ5") == 1) || t > 500)
        {
            open_map_soon(250);
            next(7);
            g_crate = 0;
        }
        break;

    case 7: /* the crates (POBJ2): M67 selected (R2, DOWN, R2), then per crate a throw */
        if (t == 400)
        {
            /* the C4 (id 151) becomes the current item (the weapon menu's choice; test shortcut
             * as boot-kit's K_FINDSEL) */
            CZKit &k = player->m_kit;
            int found = -1;

            for (int i = 0; i < k.m_num_items; i++)
                if (k.m_item[i] != NULL && (int)(u8)k.m_item[i]->m_ID == 151)
                    found = i;

            if (found >= 0)
                k.SetCurItemByIndex(found);

            SOCOM_PORT_TRACE("HOOK: read %u C4 in slot %d selected", g_reads, found);
        }

        if (t >= 600 && g_crate < 3 && g_crate < g_ncrates && g_reads >= g_next_throw)
        {
            /* event-driven (a cinematic - the klaxon after the first cache - pauses the script).
             * In front of a face of the crate stack, facing it, R1 puts the C4 on it
             * (HandleRemotePlaceExplosive: a wall within 16 of the hand), a timed charge (5 s);
             * the four faces are tried in turn until a charge is placed. */
            zdb::CNode *crate = g_crates[g_crate];
            const CBBox &b = crate->m_bbox;
            CPnt3D c((b.m_min.x + b.m_max.x) * 0.5f, b.m_min.y, (b.m_min.z + b.m_max.z) * 0.5f);

            if (g_c4_side > 0 && c4_count(player) > g_c4_base)
            {
                SOCOM_PORT_TRACE("HOOK: read %u C4 on %s from side %d", g_reads, crate->m_name, g_c4_side - 1);
                g_crate++;
                g_c4_side = 0;
                g_next_throw = g_reads + 400;
            }
            else if (g_c4_side >= 4)
            {
                SOCOM_PORT_TRACE("HOOK: read %u no C4 face found on %s", g_reads, crate->m_name);
                g_crate++;
                g_c4_side = 0;
            }
            else
            {
                CPnt3D at, dir;
                float gap = SOCOM_HOOK_C4_GAP;

                switch (g_c4_side)
                {
                case 0: at = CPnt3D(c.x, c.y, b.m_max.z + gap); dir = CPnt3D(0.0f, 0.0f, -1.0f); break;
                case 1: at = CPnt3D(c.x, c.y, b.m_min.z - gap); dir = CPnt3D(0.0f, 0.0f, 1.0f); break;
                case 2: at = CPnt3D(b.m_max.x + gap, c.y, c.z); dir = CPnt3D(-1.0f, 0.0f, 0.0f); break;
                default: at = CPnt3D(b.m_min.x - gap, c.y, c.z); dir = CPnt3D(1.0f, 0.0f, 0.0f); break;
                }

                put(player, at, dir, "crate");
                freecam_look_from(c, 45.0f, 35.0f, 45.0f);
                g_r1_pressure = 0xff;
                press(g_reads + 30, B_R1, 6);
                SOCOM_PORT_TRACE("HOOK: read %u C4 at %s (%.0f %.0f %.0f) side %d", g_reads, crate->m_name, c.x, c.y, c.z, g_c4_side);
                g_c4_base = c4_count(player);
                g_c4_side++;
                g_next_throw = g_reads + 120;
                g_cam_off = g_reads + 600;
            }
        }

        if (g_cam_off != 0 && g_reads >= g_cam_off)
        {
            freecam_off();
            g_cam_off = 0;
        }


        if ((t > 600 && val("POBJ2") == 1) || t > 3600)
        {
            freecam_off();
            next(8);
        }
        break;

    case 8: /* Pincushion: behind Snow3, the restraint (POBJ3) */
        if (snow3 == NULL)
        {
            SOCOM_PORT_TRACE("HOOK: no Snow3");
            next(99);
            break;
        }

        if (t == 30)
        {
            CPnt3D p = *snow3->GetPosW();
            const float *m = snow3->m_node->m_matrix.m_matrix[2];
            /* behind him: along his +z (he faces -z), facing his back */
            put(player, CPnt3D(p.x + m[0] * 8.0f, p.y, p.z + m[2] * 8.0f), CPnt3D(-m[0], 0.0f, -m[2]), "behind Snow3");
        }

        if (t == 60)
        {
            SOCOM_PORT_TRACE("HOOK: read %u restrain Snow3 (restrainable %d, alive %d)", g_reads, (int)snow3->m_restrainable,
                (int)snow3->m_isAlive);
            player->ExecuteAction_ApplyRestraint(snow3);
        }

        if (t == 200 || t == 400)
        {
            /* the restrained captive can surrender once he sees the player (DoReaction clears
             * his states): restrained again, now over the surrender (no new reaction then) */
            CSealCtrlAi *ai = static_cast<CSealCtrl *>(snow3->m_control)->GetSealCtrlAi();
            CAiState *s = ai != NULL ? ai->GetAiState() : NULL;
            SOCOM_PORT_TRACE("HOOK: read %u Snow3 top state %d restrained %d", g_reads, s != NULL ? (int)s->m_state : -1, (int)snow3->m_restrained);

            if (s != NULL && s->m_state != STATE_RESTRAINED)
            {
                CPnt3D p = *snow3->GetPosW();
                const float *m = snow3->m_node->m_matrix.m_matrix[2];
                put(player, CPnt3D(p.x + m[0] * 8.0f, p.y, p.z + m[2] * 8.0f), CPnt3D(-m[0], 0.0f, -m[2]), "behind Snow3 again");
                player->ExecuteAction_ApplyRestraint(snow3);
            }
        }

        if ((t > 450 && val("POBJ3") == 1) || t > 700)
            next(9);
        break;

    case 9: /* escort: in front of him, aiming at him, CMD_ESCORT to the fireteam */
        if (t == 200)
        {
            CPnt3D p = *snow3->GetPosW();
            const float *m = snow3->m_node->m_matrix.m_matrix[2];
            put(player, CPnt3D(p.x - m[0] * 15.0f, p.y, p.z - m[2] * 15.0f), CPnt3D(m[0], 0.0f, m[2]), "facing Snow3");
            /* Bravo comes along (an escortee whose master is far gives up: FollowTick's HOLDPOS) */
            put(seal_named("Bailey"), CPnt3D(p.x - m[0] * 15.0f + 10.0f, p.y, p.z - m[2] * 15.0f), CPnt3D(m[0], 0.0f, m[2]), "Bravo to Snow3");
            put(seal_named("DiMone"), CPnt3D(p.x - m[0] * 15.0f - 10.0f, p.y, p.z - m[2] * 15.0f), CPnt3D(m[0], 0.0f, m[2]), "Bravo to Snow3");
        }

        if (t >= 230 && t <= 290 && t % 10 == 0)
        {
            CZSealBody *aim = player->GetReticuleSeal();
            SOCOM_PORT_TRACE("HOOK: read %u reticule seal %s", g_reads, aim != NULL ? aim->m_node->m_name : "-");

            if (aim != snow3 && t >= 290)
            {
                /* the restrained captive sits below the standing aim: the order is given as
                 * if he were under the reticule (test only: the cached reticule seal) */
                player->m_cachedReticuleSeal = snow3;
                player->m_useCachedReticuleSeal = 1;
                aim = player->GetReticuleSeal();
                SOCOM_PORT_TRACE("HOOK: read %u reticule seal cached: %s", g_reads, aim != NULL ? aim->m_node->m_name : "-");
            }

            if (aim == snow3)
            {
                CSealUnit *unit = CSealUnit::GetUnitByTeam(1);
                SOCOM_PORT_TRACE("HOOK: read %u CMD_ESCORT to unit 1 (%p)", g_reads, (void *)unit);

                if (unit != NULL)
                    unit->IssueCommand(player, CMD_ESCORT, NULL, false);

                player->m_useCachedReticuleSeal = 0;

                /* the walk to the extraction zone (a long escort the hook does not walk): the
                 * captive, his escort and the player into the Extract region in the frame of the
                 * order, before the follower's trail check gives up on a far master */
                put_in_region(player, "Extract", 10.0f, 10.0f);
                put_in_region(seal_named("Bailey"), "Extract", -10.0f, 10.0f);
                put_in_region(seal_named("DiMone"), "Extract", 10.0f, -10.0f);
                put_in_region(snow3, "Extract", 0.0f, 0.0f);

                next(10);
            }
        }

        if (t > 300)
        {
            SOCOM_PORT_TRACE("HOOK: Snow3 never under the reticule");
            next(10);
        }
        break;

    case 10: /* extraction: Snow3 (following) into the Extract zone */
        if (t == 100)
        {
            CSealCtrlAi *ai = static_cast<CSealCtrl *>(snow3->m_control)->GetSealCtrlAi();
            CAiState *s = ai != NULL ? ai->GetAiState() : NULL;
            SOCOM_PORT_TRACE("HOOK: read %u Snow3 state %d team %08x", g_reads, s != NULL ? (int)s->m_state : -1, snow3->m_team);
            int type = -1;
            CPnt3D c;
            region_center("Extract", c, &type);
            SOCOM_PORT_TRACE("HOOK: Extract region type %d", type);
        }

        if (t > 100 && t % 60 == 0)
        {
            CSealCtrlAi *ai = static_cast<CSealCtrl *>(snow3->m_control)->GetSealCtrlAi();
            CAiState *s = ai != NULL ? ai->GetAiState() : NULL;
            SOCOM_PORT_TRACE("HOOK: read %u Snow3 state %d loc %d:%d,%d", g_reads, s != NULL ? (int)s->m_state : -1,
                (int)snow3->m_mapLocValid.m_mapid, (int)snow3->m_mapLocValid.x, (int)snow3->m_mapLocValid.y);
        }

        if (val("extract") == 1 || t > 1500)
            next(11);
        break;

    default:
        break;
    }
}
}

extern "C" float __wrap__ZN10CZSealBody22GetTerrainMotionFactorEv(CZSealBody *body)
{
    static unsigned int last_read = 0;

    if (body == ftsGetPlayer() && g_step >= 0 && g_reads != last_read)
    {
        last_read = g_reads; /* the player's motion factor is asked more than once a frame */
        script(body);
    }

    return __real__ZN10CZSealBody22GetTerrainMotionFactorEv(body);
}

extern "C" void __wrap__ZN8CMission14OnMissionStartEv(CMission *mission)
{
    __real__ZN8CMission14OnMissionStartEv(mission);
    g_new_mission = true;
    SOCOM_PORT_TRACE("HOOK: CMission::OnMissionStart (player %p)", (void *)ftsGetPlayer());
}

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
    int r = __real_scePadRead(port, slot, rdata);

    if (port != 0)
        return r;

    g_reads++;
    static const void *top_prev = NULL;
    static unsigned int top_since = 0;
    static int exit_presses = 0;
    const void *top = top_state();

    if (top != top_prev)
    {
        SOCOM_PORT_TRACE("HOOK: read %u state %s -> %s", g_reads, name_of(top_prev), name_of(top));
        top_prev = top;
        top_since = g_reads;

        if (top == &theGame.m_cinematicSubState)
            press(g_reads + 40, B_CROSS);

        if (top == &theGame.m_exitState)
            exit_presses = 0;
    }

    if (g_new_mission)
    {
        g_new_mission = false;
        g_mission++;

#ifdef SOCOM_HOOK_EXITPATHS
        next(0);
        g_sc_last_cam = 0;
        g_sc_reads = 0;
#else
        if (g_mission == 1)
            next(0);
#endif
    }

    if (top == &theGame.m_coreState)
    {
        watch_valves();

        skipcams_pad(rdata);

        /* a SELECT that skipped a camera can open the full-screen map (it pauses the game):
         * TRIANGLE closes it unless the script opened it for a look */
        static unsigned int close_at = 0;

        if (theHUD != NULL && theHUD->m_newmap.m_isFullScreen && !skipcams_playing()
            && !(g_map_at != 0 && g_reads >= g_map_at && g_reads < g_map_at + 130) && g_reads >= close_at)
        {
            SOCOM_PORT_TRACE("HOOK: read %u map open: TRIANGLE", g_reads);
            press(g_reads + 1, B_TRIANGLE);
            close_at = g_reads + 60;
        }
    }

    if (g_pause_row >= 0 && g_reads >= g_pause_from && g_reads >= g_pause_next && theHUD != NULL && theHUD->m_pausetest.m_on)
    {
        if ((int)theHUD->m_pausetest.m_curselection != g_pause_row)
            press(g_reads + 1, B_DOWN);
        else
        {
            SOCOM_PORT_TRACE("HOOK: read %u pause menu row %d: CROSS", g_reads, g_pause_row);
            press(g_reads + 1, B_CROSS);
            g_pause_row = -1;
        }

        g_pause_next = g_reads + 10;
    }

#ifdef SOCOM_HOOK_EXITPATHS
    if (top == &theGame.m_exitState && g_reads > top_since + 400 && (g_reads - top_since) % 300 == 0 && exit_presses < 4)
    {
        unsigned short b = g_mission == 1 ? B_CROSS : B_TRIANGLE;
        SOCOM_PORT_TRACE("HOOK: read %u failure debrief: %s (mission %d)", g_reads, b == B_CROSS ? "X (replay)" : "TRIANGLE (menus)", g_mission);
        press(g_reads + 1, b);
        exit_presses++;
    }
#else
    /* the success debrief: X every 300 reads (the first speeds the teletype, the next goes on
     * to dlgDebriefing when the stats are done) */
    if (top == &theGame.m_exitState && g_reads > top_since + 400 && (g_reads - top_since) % 300 == 0 && exit_presses < 4)
    {
        SOCOM_PORT_TRACE("HOOK: read %u debrief X (StatsProgress %d)", g_reads, val("StatsProgress"));
        press(g_reads + 1, B_CROSS);
        exit_presses++;
    }
#endif

    unsigned short bits = 0;

    for (int i = 0; i < g_nqueue; i++)
        if (g_reads >= g_queue[i].at && g_reads < g_queue[i].at + g_queue[i].len)
            bits |= g_queue[i].bits;

    if (bits != 0)
    {
        unsigned short held = (unsigned short)(~((rdata[2] << 8) | rdata[3]));
        held |= bits;
        rdata[2] = (unsigned char)~(held >> 8);
        rdata[3] = (unsigned char)~held;

        if (bits & B_R1)
            rdata[17] = g_r1_pressure; /* R1 pressure (the throw power) */
        if (bits & B_R2)
            rdata[19] = 0xff;
        if (bits & B_CROSS)
            rdata[14] = 0xff;
    }

    return r;
}
