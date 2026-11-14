/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): zVehicle (character roster and turrets) in m8.
 * - scePadRead: X (CROSS) skips each m8 mission camera while it plays (hook_skipcams.h detects
 *   them); a trace every 600 reads (player position, alive, health; the heap is on every line).
 * - -DSOCOM_HOOK_TURRET: m8 has no turret node, so after CMission::LoadVehicles' CTurret::LoadTurrets
 *   this puts one (the demo_turret definition, hostile to the player) on the nearest world node
 *   that has a child with a child (yaw part = child, barrel and fire point = grandchild), and
 *   traces it every 150 reads: target, aim dot, shots, the player's health.
 *   -DSOCOM_HOOK_TURRET_CAM: the test camera looks at that node. */
#include "gamez/zSeal/zseal.h"
#include "gamez/zFTS/zfts.h"
#include "gamez/zVehicle/zvehicle.h"
#include "gamez/zNode/node_world.h"
#include "hook_skipcams.h"
#ifdef SOCOM_HOOK_TURRET_CAM
#define HOOK_FREECAM_WRAP
#include "hook_freecam.h"
#endif

extern "C" int __real_scePadRead(int port, int slot, unsigned char *rdata);

static unsigned int g_reads;
static unsigned int g_cross_press;
static int g_cross_left;

#ifdef SOCOM_HOOK_TURRET
static CTurret *g_turret;
static zdb::CNode *g_tnode;

static void find_node(zdb::CNode *node, const CPnt3D &at, zdb::CNode *&best, f32 &bestd)
{
	if (node == NULL)
		return;

	for (zdb::CNodeVector::iterator i = node->m_child.begin(); i != node->m_child.end(); ++i)
	{
		zdb::CNode *c = *i;

		if (c == NULL)
			continue;

		if (c->m_name != NULL && c->m_child.size() != 0 && c->m_child[0] != NULL && c->m_child[0]->m_name != NULL
			&& c->m_child[0]->m_child.size() == 0 && c->m_parent != NULL)
		{
			zdb::CNode *g = c->m_child[0];
			CMatrix m;

			if (g->BuildMTW(m) != NULL)
			{
				f32 dx = m.m_matrix[3][0] - at.x, dz = m.m_matrix[3][2] - at.z;
				f32 d = dx * dx + dz * dz;

				if (d > 300.0f * 300.0f && d < bestd)
				{
					bestd = d;
					best = c;
				}
			}
		}

		find_node(c, at, best, bestd);
	}
}
#endif

extern "C" int __wrap_scePadRead(int port, int slot, unsigned char *rdata)
{
	int r = __real_scePadRead(port, slot, rdata);

	if (port != 0)
		return r;

	g_reads++;

	/* X skips the mission camera (pressed once a second while one plays) */
	if (skipcams_playing() && g_reads >= g_cross_press + 30)
	{
		g_cross_press = g_reads;
		g_cross_left = 3;
		SOCOM_PORT_TRACE("HOOK: X skips mission camera %s at read %u",
			theHUD->m_missioncams.m_currentcam != NULL ? theHUD->m_missioncams.m_currentcam->m_identifier : "-", g_reads);
	}

	if (g_cross_left > 0)
	{
		rdata[3] &= (unsigned char)~0x40; /* CROSS (active low) */
		g_cross_left--;
	}

	CZSealBody *player = ftsGetPlayer();

	if (player != NULL && (g_reads % 600) == 0)
		SOCOM_PORT_TRACE("HOOK: r%u player at %.0f %.0f %.0f alive %d health %.2f", g_reads, player->GetPosW()->x,
			player->GetPosW()->y, player->GetPosW()->z, (int)player->m_isAlive, player->m_health);

#ifdef SOCOM_HOOK_TURRET
	if (g_turret != NULL && (g_reads % 150) == 0)
	{
		CEntity *t = g_turret->m_target.m_target.m_ent;
		SOCOM_PORT_TRACE("HOOK: r%u turret active %d enabled %d targets %u target %s dist %.0f aimdot %.2f shots %d trig %.2f/%.2f fire %.2f firepos %.0f %.0f %.0f player health %.2f",
			g_reads, (int)g_turret->m_active, (int)g_turret->m_enabled, (u32)g_turret->m_targets.size(),
			t != NULL && t->m_node != NULL && t->m_node->m_name != NULL ? t->m_node->m_name : "-",
			g_turret->m_target.m_target.m_dist, g_turret->m_aimdot, g_turret->m_shots, g_turret->m_trigger.m_timer,
			g_turret->m_trigger.m_marker, g_turret->m_fire_timer.m_timer, g_turret->m_firepos.x, g_turret->m_firepos.y,
			g_turret->m_firepos.z, player != NULL ? player->m_health : -1.0f);
	}

#ifdef SOCOM_HOOK_TURRET_CAM
	if (g_turret != NULL && !skipcams_playing())
		freecam_look_from(g_turret->m_firepos, 300.0f, 200.0f, 300.0f);
#endif
#endif

	return r;
}

#ifdef SOCOM_HOOK_TURRET
extern "C" void __real__ZN7CTurret11LoadTurretsEv();

extern "C" void __wrap__ZN7CTurret11LoadTurretsEv()
{
	__real__ZN7CTurret11LoadTurretsEv();
	CZSealBody *player = ftsGetPlayer();
	CTurretDef *def = CTurret::m_turret_def.size() != 0 ? &CTurret::m_turret_def[0] : NULL;

	if (player == NULL || def == NULL)
	{
		SOCOM_PORT_TRACE("HOOK: turret: no player or no definition");
		return;
	}

	zdb::CNode *best = NULL;
	f32 bestd = 1.0e12f;
	find_node(zdb::CWorld::m_world, *player->GetPosW(), best, bestd);

	if (best == NULL)
	{
		SOCOM_PORT_TRACE("HOOK: turret: no node");
		return;
	}

	CTurretDef test = *def;
	strncpy(test.m_parts[0], best->m_child[0]->m_name, 31);
	strncpy(test.m_parts[1], best->m_child[0]->m_name, 31);
	strncpy(test.m_parts[2], best->m_child[0]->m_name, 31);
	zdb::CNode *host = best->m_parent;
	g_turret = new CTurret(host, test);
	/* the parts are looked up below the host: yaw part = best's child is too deep, so point
	 * them at best (yaw) and its child (barrel, fire point) */
	g_turret->m_turret = best;
	g_turret->m_barrel = best->m_child[0];
	g_turret->m_firepoint = best->m_child[0];
	CEntity::CreateEntity(g_turret, false);
	g_tnode = best;
	SOCOM_PORT_TRACE("HOOK: turret %s (team 0x%x, weapon %s %p ammo %p, range %.0f, fov %.2f, acc %.2f) on %s / %s under %s, %.0f from the player",
		def->m_name, g_turret->m_team, def->m_weapon, g_turret->m_weapon, g_turret->m_ammo, g_turret->m_aiParams.visual_range,
		g_turret->m_aiParams.visual_fov, g_turret->m_aiParams.accuracy, best->m_name, best->m_child[0]->m_name,
		host->m_name != NULL ? host->m_name : "-", sqrtf(bestd));

	for (CTurretDefVector::iterator i = CTurret::m_turret_def.begin(); i != CTurret::m_turret_def.end(); ++i)
		SOCOM_PORT_TRACE("HOOK: def %s parts %s/%s/%s weapon %s ammo %s yaw %.2f %.2f pitch %.2f %.2f health %.0f team 0x%x trig %.2f+%.2f %.2f+%.2f acc %.2f range %.0f",
			i->m_name, i->m_parts[0], i->m_parts[1], i->m_parts[2], i->m_weapon, i->m_ammo, i->m_yaw[0], i->m_yaw[1],
			i->m_pitch[0], i->m_pitch[1], i->m_health, i->m_team, i->m_trigger.m_up_time.m_min, i->m_trigger.m_up_time.m_range,
			i->m_trigger.m_dn_time.m_min, i->m_trigger.m_dn_time.m_range, i->m_aiParams.accuracy, i->m_aiParams.visual_range);
}
#endif
