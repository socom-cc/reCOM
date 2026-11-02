/* Unbuilt holding file (stage 5 BD4): provisional code that owns no planned artifact, held here by order skeleton write. */

/* @socom-skeleton body g_assetsRecycle__3zdb */
/* held from src/gamez/zNode/node_assetlib.cpp:32 */
namespace zdb {
CAssetList g_assetsRecycle;
}

/* @socom-skeleton body numNodes__3zdb */
/* held from src/gamez/zNode/node_main.cpp:21 */
namespace zdb {
u32 numNodes = 0;
}

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
CBBox* CNode::GetBBox()
	{
		if (m_use_parent_bbox)
		{
			return m_parent->GetBBox();
		}

		return &m_bbox;
	}
}

/* @socom-skeleton body Exists__Q23zdb11CNodeVectorCFPCQ23zdb5CNode */
/* held from src/gamez/zNode/node_main.cpp:889 */
namespace zdb {
bool CNodeVector::Exists(const CNode* node) const
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
CNode* CNodeVector::GetNode(const char* name) const
	{
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
					found = strcmp(name, node->m_name);
				}

				if (found)
				{
					break;
				}
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

		insert(begin(), universeNode);

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
CNode* CNodeUniverse::GetElement(s32 index) const
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
u32 CNodeUniverse::GetIndex(CNode* node) const
	{
		u32 index = 0;
		for (auto i = begin(); i != end(); ++i)
		{
			index++;

			if (*i != node)
				continue;

			return index;
		}

		return 0;
	}
}

/* @socom-skeleton body Reset__Q23zdb5CWindFv */
/* held from src/gamez/zNode/node_wind.cpp:5 */
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

/* @socom-skeleton body GetTexHandle__Q23zdb6CWorldFPc */
/* held from src/gamez/zNode/node_world.cpp:235 */
namespace zdb {
CTexHandle* CWorld::GetTexHandle(char* name)
	{
		return CAssetMgr::m_assets.GetTexHandle(name);
	}
}
