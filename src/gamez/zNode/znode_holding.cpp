/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

#include <string.h>
#include <algorithm>
#include "gamez/zNode/znode.h"
#include "gamez/zNode/node_model.h"
#include "gamez/zNode/node_universe.h"
#include "gamez/zNode/node_world.h"
#include "gamez/zNode/node_assetlib.h"

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

/* @socom-skeleton body GetTexHandle__Q23zdb6CWorldFPc */
/* held from src/gamez/zNode/node_world.cpp:235 */
namespace zdb {
CTexHandle* CWorld::GetTexHandle(const char* name) /* port: GetTexHandle__Q23zdb6CWorldFPCc */
	{
		return CAssetMgr::m_assets.GetTexHandle(name);
	}
}
