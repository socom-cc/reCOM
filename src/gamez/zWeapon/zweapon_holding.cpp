/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */
#include "gamez/zWeapon/zweapon.h"

/* @socom-skeleton body personMaterialId__4zwep */
/* held from src/gamez/zWeapon/zwep_global.cpp:5 */
namespace zwep {
u32 personMaterialId = 0xffffffff;
}

/* port: no stage-4 owner - m_weaponTickDisabled 0x476688 and m_pProjectilelist 0x47667c
   (.sbss; the weapon pre/post-tick tasks read them) */
bool CZWeapon::m_weaponTickDisabled;
CZProjectileList* CZWeapon::m_pProjectilelist;

/* @socom-skeleton body m_timer_bTimerRegistered__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:8 */
bool CZWeapon::m_timer_bTimerRegistered = false;

/* @socom-skeleton body m_timer_bTimerCleared__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:9 */
bool CZWeapon::m_timer_bTimerCleared = false;

/* @socom-skeleton body m_timer_bIncrTimer__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:10 */
bool CZWeapon::m_timer_bIncrTimer = false;

/* @socom-skeleton body m_timer_pCurval__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:11 */
f32 CZWeapon::m_timer_pCurval = 0.0f;

/* @socom-skeleton body m_timer_maxval__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:12 */
f32 CZWeapon::m_timer_maxval = 0.0f;

/* @socom-skeleton body m_allowFireAnimations__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:14 */
bool CZWeapon::m_allowFireAnimations = false;

/* @socom-skeleton body m_allowImpactAnimations__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:15 */
bool CZWeapon::m_allowImpactAnimations = false;

/* @socom-skeleton body m_allowWeaponIntersection__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:16 */
bool CZWeapon::m_allowWeaponIntersection = false;

/* @socom-skeleton body version__Q28CZWeapon9AI_PARAMS */
/* held from src/gamez/zWeapon/zwep_global.cpp:18 */
u32 CZWeapon::AI_PARAMS::version = 1;

/* @socom-skeleton body m_bulletPassSound__8CZWeapon */
/* held from src/gamez/zWeapon/zwep_global.cpp:19 */
CSnd* CZWeapon::m_bulletPassSound = NULL;
