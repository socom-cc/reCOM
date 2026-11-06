#ifndef NODE_UNIVERSE_H
#define NODE_UNIVERSE_H
#include <vector>

#include "znode.h"

namespace zdb
{
	class CNodeUniverse : public std::vector<CNode*>
	{
	public:
		enum { MIN_POOL_SIZE = 3000, POOL_INCREMENT = 100 }; /* port: AddNode 0x224684 (0xbb8, 0x64) */
		bool AddNode(CNode* node);
		void RemoveNode(CNode* node);
		CNode* GetElement(s32 index);
		u32 GetIndex(CNode* node);
	public:
		bool m_locked;
	};
}
#endif