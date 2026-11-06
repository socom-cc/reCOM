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
		m_active = active;
		return m_active;
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

/* @socom-skeleton body Exists__Q23zdb11CNodeVectorCFPCQ23zdb5CNode */
/* held from src/gamez/zNode/node_main.cpp:889 */
namespace zdb {
bool CNodeVector::Exists(const CNode* node) /* port: the ELF has only Exists__Q23zdb11CNodeVectorFPCQ23zdb5CNode */
	{
		auto it = begin();
		auto last = end();

		while (it != last)
		{
			if (*it == node)
			{
				break;
			}

			it++;
		}

		return it != last;
	}
}

/* @socom-skeleton body GetNode__Q23zdb11CNodeVectorCFPCc */
/* held from src/gamez/zNode/node_main.cpp:907 */
namespace zdb {
CNode* CNodeVector::GetNode(const char* name) /* port: the ELF has only GetNode__Q23zdb11CNodeVectorFPCc */
	{
		/* port: loop fixed from 0x224350 - advance the iterator; match when strcmp(...) == 0 */
		CNode* node = NULL;

		if (!name)
		{
			return NULL;
		}
		else
		{
			auto it = begin();
			auto last = end();

			while (it != last)
			{
				CNode* node = *it;
				bool found = false;

				if (node != NULL && node->m_name != 0)
				{
					found = strcmp(name, node->m_name) == 0;
				}

				if (found)
				{
					break;
				}

				it++;
			}

			if (it != last)
			{
				node = *it;
			}
		}

		return node;
	}
}

/* @socom-skeleton body Remove__Q23zdb11CNodeVectorFPCQ23zdb5CNode */
/* held from src/gamez/zNode/node_main.cpp:945 */
namespace zdb {
bool CNodeVector::Remove(const CNode* node)
	{
		auto it = begin();
		auto last = end();

		for (; it != last; it++)
		{
			if (*it == node)
			{
				break;
			}
		}

		const CNode* found = node;

		if (it != last)
		{
			it = std::remove_copy(it + 1, last, it, found);
		}

		erase(it, last);

		return it != last;
	}
}

/* @socom-skeleton body GetModel__Q23zdb12CModelVectorFPCc */
/* held from src/gamez/zNode/node_model.cpp:66 */
namespace zdb {
CModel* CModelVector::GetModel(const char* name)
	{
		CModel* model = NULL;

		if (name == NULL)
		{
			model = NULL;
		}
		else
		{
			for (auto it = begin(); it != end(); it++)
			{
				if (strcmp(name, (*it)->m_name) == 0)
				{
					model = *it;
					break;
				}
			}
		}

		return model;
	}
}

/* @socom-skeleton body AddNode__Q23zdb13CNodeUniverseFPQ23zdb5CNode */
/* held from src/gamez/zNode/node_universe.cpp:10 */
namespace zdb {
bool CNodeUniverse::AddNode(CNode* node)
	{
		if (m_locked)
			return false;

		CNode* universeNode = node;
		u32 universeSize = size();

		if (universeSize == capacity())
		{
			if (capacity() < MIN_POOL_SIZE)
				reserve(MIN_POOL_SIZE);
			else
				reserve(capacity() + POOL_INCREMENT);
		}

		insert(end(), universeNode); /* port: 0x2246d0 inserts at data + size */

		return true;
	}
}

/* @socom-skeleton body RemoveNode__Q23zdb13CNodeUniverseFPQ23zdb5CNode */
/* held from src/gamez/zNode/node_universe.cpp:31 */
namespace zdb {
void CNodeUniverse::RemoveNode(CNode* node)
	{
		for (auto i = begin(); i != end(); ++i)
		{
			if (*i == node)
			{
				*i = NULL;
				break;
			}
		}
	}
}

/* @socom-skeleton body GetElement__Q23zdb13CNodeUniverseCFi */
/* held from src/gamez/zNode/node_universe.cpp:43 */
namespace zdb {
CNode* CNodeUniverse::GetElement(s32 index) /* port: the ELF has only GetElement__Q23zdb13CNodeUniverseFi */
	{
		CNode* node;

		if (index < 0)
			return NULL;

		if (index <= size())
			return at(index);

		return NULL;
	}
}

/* @socom-skeleton body GetIndex__Q23zdb13CNodeUniverseCFPQ23zdb5CNode */
/* held from src/gamez/zNode/node_universe.cpp:56 */
namespace zdb {
u32 CNodeUniverse::GetIndex(CNode* node) /* port: the ELF has only GetIndex__Q23zdb13CNodeUniverseFPQ23zdb5CNode */
	{
		/* port: 0x2245c0 returns the 0-based position, or -1 when absent */
		u32 index = 0;
		for (auto i = begin(); i != end(); ++i, index++)
		{
			if (*i == node)
				return index;
		}

		return (u32)-1;
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
