/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include <string.h>
#include <algorithm>
#include "gamez/zNode/znode.h"
#include "gamez/zNode/node_model.h"
#include "gamez/zNode/node_universe.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zNode/node_assetlib.h"

/* @socom-skeleton body g_assetsRecycle__3zdb */
/* held from src/gamez/zNode/node_assetlib.cpp:32 */
/* port: duplicate of gamez/zNode/node_assetlib.cpp (g_assetsRecycle__Q23zdb27@unnamed@node_assetlib_cpp@) */
#if 0
namespace zdb {
CAssetList g_assetsRecycle;
}
#endif

/* @socom-skeleton body numNodes__3zdb */
/* held from src/gamez/zNode/node_main.cpp:21 */
/* port: duplicate of gamez/zNode/node_main.cpp (ELF numNodes) */
#if 0
namespace zdb {
u32 numNodes = 0;
}
#endif

/* @socom-skeleton body SetActive__Q23zdb5CNodeFb */
/* held from src/gamez/zNode/node_main.cpp:671 */
namespace zdb {
bool CNode::SetActive(bool active)
	{
		/* 0x17d2b0: returns the previous state (callers such as CZSealBody::SealGetAltitude
		   0x2a2250 restore it); port fix: returned the new one */
		bool was = m_active;
		m_active = active;
		return was;
	}
}

/* @socom-skeleton body GetBBox__Q23zdb5CNodeFv */
/* held from src/gamez/zNode/node_main.cpp:715 */
namespace zdb {
CBBox* CNode::GetBBox() const /* port: the ELF has only GetBBox__Q23zdb5CNodeCFv */
	{
		if (m_use_parent_bbox)
		{
			return m_parent->GetBBox();
		}

		return const_cast<CBBox*>(&m_bbox);
	}
}

/* @socom-skeleton body Reset__Q23zdb5CWindFv */
/* held from src/gamez/zNode/node_wind.cpp:5 */
/* port: duplicate of gamez/zNode/node_world.cpp (ELF Reset__5CWindFv; CWind is global) */
#if 0
namespace zdb {
void CWind::Reset()
	{
		m_ZenithGoal = 0.0f;
		m_AzimuthGoal = 0.0f;
		m_SpeedGoal = 0.0f;
		m_TickGoal = false;

		m_Zenith = 0.0f;
		m_Azimuth = 0.0f;
		m_Speed = 8.0f;

		m_AzimuthOffset = 0.0f;
		m_MinAzimuthOffset = -0.7853982f;
		m_MaxAzimuthOffset = 0.7853982f;

		m_ZenithOffset = 0.0f;
		m_MinZenithOffset = -0.7853982f;
		m_MaxZenithOffset = 0.7853982f;

		m_AzimuthOffsetVelocity = 0.2617994f;
		m_ZenithOffsetVelocity = 0.08726646f;

		m_SpeedOffset = 3.0f;
		m_MinSpeedOffset = -7.5f;
		m_MaxSpeedOffset = 9.0f;
		m_SpeedOffsetVelocity = 3.0f;
	}
}
#endif

/* @socom-skeleton body GetTexHandle__Q23zdb6CWorldFPc */
/* held from src/gamez/zNode/node_world.cpp:235 */
namespace zdb {
CTexHandle* CWorld::GetTexHandle(const char* name) /* port: GetTexHandle__Q23zdb6CWorldFPCc */
	{
		return CAssetMgr::m_assets.GetTexHandle(name);
	}
}
