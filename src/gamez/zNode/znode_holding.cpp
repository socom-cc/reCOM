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
/* port: deleted (was #if 0): duplicate of gamez/zNode/node_assetlib.cpp (g_assetsRecycle__Q23zdb27@unnamed@node_assetlib_cpp@) */

/* @socom-skeleton body numNodes__3zdb */
/* held from src/gamez/zNode/node_main.cpp:21 */
/* port: deleted (was #if 0): duplicate of gamez/zNode/node_main.cpp (ELF numNodes) */

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
/* port: deleted (was #if 0): duplicate of gamez/zNode/node_world.cpp (ELF Reset__5CWindFv; CWind is global) */

/* @socom-skeleton body GetTexHandle__Q23zdb6CWorldFPc */
/* held from src/gamez/zNode/node_world.cpp:235 */
namespace zdb {
CTexHandle* CWorld::GetTexHandle(const char* name) /* port: GetTexHandle__Q23zdb6CWorldFPCc */
	{
		return CAssetMgr::m_assets.GetTexHandle(name);
	}
}
