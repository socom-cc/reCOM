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
		/* port: GetElement/GetIndex are declared in the region below (GetElement__Q23zdb13CNodeUniverseFi, GetIndex__Q23zdb13CNodeUniverseFPQ23zdb5CNode) */
	public:
		bool m_locked;
		/* @socom-skeleton decl Q23zdb13CNodeUniverse */
public:
		int GetIndex(zdb::CNode *);
		zdb::CNode * GetElement(int);
		/* @socom-skeleton end Q23zdb13CNodeUniverse */
	};
}
#endif