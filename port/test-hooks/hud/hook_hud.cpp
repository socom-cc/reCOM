/* TEST-ONLY HOOK (functional port lane). Linked with -Wl,--wrap into scratch test builds only
 * (port/test-hooks/<feature>/build.sh -> port/tools/dev/hook.sh); never part of a normal build and
 * never compiled by port/CMakeLists.txt. It may use `#define private public` to reach game internals
 * and rewrites game state for the test: its results are behaviour checks, never matching evidence. */
/* TEST HOOK (test only): stand-ins for the non-void stubs the HUD tick
 * reaches in other workers' files, so the HUD can be tested before they are written. Each
 * follows the ELF where it is trivial (cited), otherwise returns the ELF's value for the
 * m8 single-player start state. Linked with -Wl,--wrap=<mangled> (cross-unit calls only). */
#define private public
#define protected public
#include "gamez/zSeal/zseal.h"
#include "gamez/zWeapon/zweapon.h"
#include "gamez/zEntity/zentity.h"
#include "Apps/FTS/hud/hud.h"

extern "C" void socom_port_trace(const char *fmt, ...);

/* CZKit::GetCurItem 0x2abd40: lw 2056(a0) (m_selected_item), m_item[] at +208 */
extern "C" CZFTSWeapon* __wrap__ZNK5CZKit10GetCurItemEv(const CZKit* kit)
{
	return kit->m_item[kit->m_selected_item];
}

/* CZKit::GetCurAmmoCount 0x2abed0: only reached with a throwable item (none load yet) */
extern "C" int __wrap__ZN5CZKit15GetCurAmmoCountEv(CZKit*)
{
	return 0;
}

/* OrdersMenu::HandlePad 0x175ff0: the radio command menu (3312 bytes); 0 = no command */
extern "C" int __wrap__ZN10OrdersMenu9HandlePadEP4CPadf(OrdersMenu*, CPad*, float)
{
	return 0;
}

/* CZWeapon::TimerCleared 0x31c9a0 / TimerRegistered 0x31c9d0: lbu of the static flags */
extern "C" unsigned char __wrap__ZN8CZWeapon12TimerClearedEv()
{
	return CZWeapon::m_timer_bTimerCleared;
}

extern "C" unsigned char __wrap__ZN8CZWeapon15TimerRegisteredEv()
{
	return CZWeapon::m_timer_bTimerRegistered;
}

/* CZSealBody::GetReticuleSeal 0x29a800: cached reticule seal or GetSeal(reticule DI node);
 * the reticule DI is not computed in the port yet: none */
extern "C" CZSealBody* __wrap__ZN10CZSealBody15GetReticuleSealEv(CZSealBody*)
{
	return NULL;
}

/* CSealUnit::GetUnitByTeam 0x2d7590 walks CSealUnit::m_list for m_unit_num == team; the
 * port creates no units yet (CreateSinglePlayerUnits is a stub): none */
extern "C" CSealUnit* __wrap__ZN9CSealUnit13GetUnitByTeamEj(unsigned int)
{
	return NULL;
}

extern "C" CZSealBody* __wrap__ZN9CSealUnit14GetSealByIndexEj(CSealUnit*, unsigned int)
{
	return NULL;
}

/* CEntityList::GetEntityById 0x1ee190: only reached when the player is dead */
extern "C" CEntity* __wrap__ZNK11CEntityList13GetEntityByIdEj(const CEntityList*, unsigned int)
{
	return NULL;
}

extern "C" CTarget* __wrap__ZN11CTargetList10FindTargetEP7CEntity(CTargetList*, CEntity*)
{
	return NULL;
}
